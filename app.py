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
from reportlab.pdfbase.ttfonts import TTFont
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
# 【修正】日本語フォント確保（Google Fonts利用）
# ==========================================
def get_valid_japanese_font():
    # 以前の壊れたファイルがあれば削除する（クリーンアップ）
    old_font = "IPAexGothic.ttf"
    if os.path.exists(old_font):
        os.remove(old_font)

    font_filename = "NotoSansJP-Regular.ttf"
    # Google Fontsの公式Rawデータ（安定・高速）
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Regular.ttf"
    
    # ファイルがない、またはサイズがおかしい場合は再ダウンロード
    if not os.path.exists(font_filename) or os.path.getsize(font_filename) < 1000:
        try:
            # 以前の残骸を消す
            if os.path.exists(font_filename):
                os.remove(font_filename)
                
            response = requests.get(font_url, timeout=30)
            if response.status_code == 200:
                with open(font_filename, "wb") as f:
                    f.write(response.content)
            else:
                return None
        except Exception:
            return None
            
    # 最終チェック：ファイルが存在し、サイズが十分か
    if os.path.exists(font_filename) and os.path.getsize(font_filename) > 1000000:
        return font_filename
    else:
        return None

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
    
    # フォント準備
    font_path = get_valid_japanese_font()
    font_name = 'Helvetica' # 初期値（これだと文字化けする）
    
    if font_path:
        try:
            # フォント登録を試みる
            pdfmetrics.registerFont(TTFont('Japanese', font_path))
            font_name = 'Japanese'
        except Exception as e:
            # フォント自体が壊れている場合
            print(f"Font error: {e}")
            return None, False
    else:
        # フォントがダウンロードできなかった場合
        # 壊れたPDFを作るくらいなら失敗として返す
        return None, False

    styles = getSampleStyleSheet()
    
    # 日本語対応スタイル
    style_body = ParagraphStyle(name='JapaneseBody',
                                parent=styles['Normal'],
                                fontName=font_name,
                                fontSize=10.5,
                                leading=16,
                                spaceAfter=6,
                                alignment=TA_JUSTIFY)
                                
    style_title = ParagraphStyle(name='JapaneseTitle',
                                 parent=styles['Heading1'],
                                 fontName=font_name,
                                 fontSize=16,
                                 leading=20,
                                 spaceAfter=20)

    story = []
    
    # タイトル
    story.append(Paragraph(title, style_title))
    
    # 本文
    for text in clean_text_list:
        if text.strip():
            # 特殊文字エスケープ
            safe_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Paragraph(safe_text, style_body))
            story.append(Spacer(1, 2*mm))

    try:
        doc.build(story)
        buffer.seek(0)
        return buffer, True # 成功
    except Exception:
        return None, False

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
st.set_page_config(page_title="H-Review Pro", layout="centered")

st.title("💎 コンテンツ抽出アプリ")
st.caption("抽出後、下のボタンから保存できます。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

# 全幅ボタン
if st.button("抽出を開始する", type="primary", use_container_width=True):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.info("⏳ サイトを解析中... (10〜20秒かかります)")
        
        html = fetch_html_force_clean(url)

        if html:
            status.info("📄 データ生成中...")
            
            page_title, article_title, text_list, final_html = extract_target_content(html, url)
            
            # --- 処理完了 ---
            status.empty()
            st.success("抽出完了！")
            
            # === 保存ボタンエリア ===
            col1, col2 = st.columns(2)
            
            with col1:
                # Word
                docx_file = create_docx(article_title, text_list)
                st.download_button(
                    label="📄 Wordで保存",
                    data=docx_file,
                    file_name="story.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True 
                )
            
            with col2:
                # PDF
                pdf_file, pdf_success = create_pdf(article_title, text_list)
                
                if pdf_success:
                    st.download_button(
                        label="📕 PDFで保存",
                        data=pdf_file,
                        file_name="story.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    # フォントダウンロード失敗時
                    st.error("⚠️ PDF用のフォント取得に失敗しました。時間をおいて試すか、Word保存をご利用ください。")
            
            st.divider()
            
            # プレビュー表示
            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
