import streamlit as st
import streamlit.components.v1 as components
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import subprocess
import os
import requests
from io import BytesIO

# Word/PDF作成用
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY

# ==========================================
# 設定：入り口URL
# ==========================================
FIXED_ENTRY_URL = "https://www.h-ken.net/mypage/20250611_1605697556/"

# ==========================================
# サーバー設定
# ==========================================
def install_playwright():
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Install error: {e}")

if "setup_done" not in st.session_state:
    with st.spinner("サーバー起動中..."):
        install_playwright()
        st.session_state.setup_done = True

# ==========================================
# 【修正】日本語フォント確保（自己修復機能付き）
# ==========================================
def ensure_japanese_font():
    font_filename = "IPAexGothic.ttf"
    # より安定したURLに変更（GitHubのRawデータ）
    font_url = "https://raw.githubusercontent.com/minoryorg/ipaex-font/master/ipaexg.ttf"
    
    # 1. 壊れたファイルが残っていたら削除するチェック
    if os.path.exists(font_filename):
        # サイズが小さすぎる(1MB以下)場合は、失敗したゴミファイルとみなして消す
        if os.path.getsize(font_filename) < 1000 * 1000:
            os.remove(font_filename)

    # 2. ファイルがなければダウンロード
    if not os.path.exists(font_filename):
        try:
            response = requests.get(font_url, timeout=30)
            if response.status_code == 200:
                with open(font_filename, "wb") as f:
                    f.write(response.content)
            else:
                return None
        except Exception:
            return None
            
    return font_filename if os.path.exists(font_filename) else None

# ==========================================
# Wordファイル作成
# ==========================================
def create_docx(title, clean_text_list):
    doc = Document()
    doc.add_heading(title, 0)
    
    for text in clean_text_list:
        if text.strip():
            doc.add_paragraph(text)
            
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ==========================================
# PDFファイル作成
# ==========================================
def create_pdf(title, clean_text_list):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    
    # フォント読み込み（失敗時は英語フォントへ逃げる）
    font_path = ensure_japanese_font()
    font_name = 'Helvetica' # デフォルト
    
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont('Japanese', font_path))
            font_name = 'Japanese'
        except TTFError:
            # 万が一フォントが壊れていたら削除して次回に備える
            if os.path.exists(font_path):
                os.remove(font_path)
            # 今回は英語フォントで進める（エラーで止まるよりはマシ）
            pass

    styles = getSampleStyleSheet()
    
    # スタイル定義
    style_body = ParagraphStyle(name='Body',
                                parent=styles['Normal'],
                                fontName=font_name,
                                fontSize=10.5,
                                leading=16,
                                spaceAfter=6,
                                alignment=TA_JUSTIFY)
                                
    style_title = ParagraphStyle(name='Title',
                                 parent=styles['Heading1'],
                                 fontName=font_name,
                                 fontSize=16,
                                 leading=20,
                                 spaceAfter=20)

    story = []
    
    # PDF生成
    story.append(Paragraph(title, style_title))
    
    for text in clean_text_list:
        if text.strip():
            # 特殊文字エスケープ
            safe_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Paragraph(safe_text, style_body))
            story.append(Spacer(1, 2*mm))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ==========================================
# ブラウザ操作
# ==========================================
def fetch_html_force_clean(target_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        iphone_12 = p.devices['iPhone 12']
        context = browser.new_context(**iphone_12)
        page = context.new_page()

        try:
            page.goto(FIXED_ENTRY_URL, timeout=30000)
            time.sleep(2) 
            page.goto(target_url, timeout=30000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2) 

            # ポップアップ破壊
            page.evaluate("""
                () => {
                    const keywords = ['はい', 'YES', 'Yes', '18歳', 'Enter', '入り口', '入場'];
                    const buttons = document.querySelectorAll('a, button, div, span');
                    for (let btn of buttons) {
                        if (keywords.some(k => btn.innerText && btn.innerText.includes(k))) {
                            btn.click();
                        }
                    }
                    const allDivs = document.querySelectorAll('body > div, body > section');
                    allDivs.forEach(div => {
                        const style = window.getComputedStyle(div);
                        if (style.position === 'fixed' && style.zIndex > 50) {
                            div.remove();
                        }
                    });
                    document.body.style.overflow = 'visible';
                    document.body.style.height = 'auto';
                }
            """)
            time.sleep(1) 
            return page.content()
        except Exception as e:
            st.error(f"エラー: {e}")
            return None
        finally:
            browser.close()

# ==========================================
# 抽出ロジック
# ==========================================
def extract_target_content(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    styles = []
    for link in soup.find_all('link', rel='stylesheet'):
        styles.append(str(link))
    for style in soup.find_all('style'):
        styles.append(str(style))
    style_html = "\n".join(styles)

    # タイトル
    title_html = ""
    title_text_clean = "タイトルなし"
    target_h1 = soup.find("h1", class_="pageTitle")
    
    if target_h1:
        title_html = str(target_h1)
        title_text_clean = target_h1.get_text(strip=True)
    else:
        target_h1 = soup.find("h1")
        if target_h1:
            title_html = str(target_h1)
            title_text_clean = target_h1.get_text(strip=True)

    simple_title_text = soup.title.get_text(strip=True) if soup.title else "抽出結果"

    # 本文
    body_html = "<div>本文が見つかりませんでした</div>"
    text_list_for_file = []
    
    target_div = soup.find(id="sentenceBox")
    if not target_div:
        target_div = soup.find(id="main_txt")

    if target_div:
        for bad in target_div.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
            bad.decompose()

        cut_point = target_div.find(class_="kakomiPop2")
        if cut_point:
            for sibling in cut_point.find_next_siblings():
                sibling.decompose()
            cut_point.decompose()

        body_html = str(target_div)
        
        for elem in target_div.find_all(['p', 'div', 'h2', 'h3', 'br']):
            txt = elem.get_text(strip=True)
            if txt:
                text_list_for_file.append(txt)

    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <base href="{target_url}">
        {style_html}
        <style>
            body {{
                background-color: #fff;
                padding: 15px;
                font-family: sans-serif;
                overflow: auto !important;
            }}
            h1.pageTitle {{
                font-size: 20px;
                margin-bottom: 20px;
                border-bottom: 1px solid #ccc;
                padding-bottom: 10px;
                line-height: 1.4;
            }}
            #sentenceBox {{
                font-size: 16px;
                line-height: 1.8;
                color: #333;
            }}
        </style>
    </head>
    <body>
        {title_html}
        {body_html}
    </body>
    </html>
    """

    return simple_title_text, title_text_clean, text_list_for_file, final_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Pro", layout="wide")

st.title("💎 完全版リーダー (修復機能付き)")
st.caption("抽出・表示・Word/PDF保存が可能です。")

col1, col2 = st.columns([3, 1])
with col1:
    url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出する", type="primary"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("読み込み中...")
        
        html = fetch_html_force_clean(url)

        if html:
            status.text("データ生成中...")
            
            page_title, article_title, text_list, final_html = extract_target_content(html, url)
            
            status.empty()
            st.success("完了")
            
            st.sidebar.markdown("### 📥 ダウンロード")
            
            # Word
            docx_file = create_docx(article_title, text_list)
            st.sidebar.download_button(
                label="📄 Word (.docx) で保存",
                data=docx_file,
                file_name="story.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
            # PDF
            pdf_file = create_pdf(article_title, text_list)
            st.sidebar.download_button(
                label="📕 PDF (.pdf) で保存",
                data=pdf_file,
                file_name="story.pdf",
                mime="application/pdf"
            )

            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
