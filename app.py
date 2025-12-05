import streamlit as st
import streamlit.components.v1 as components
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, NavigableString, Tag
import time
import subprocess
import os
import re
from io import BytesIO

# Word作成用
from docx import Document
from docx.shared import RGBColor, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

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
# 【新機能】HTMLの色をWordの色に変換するロジック
# ==========================================
def parse_color(style_str):
    """style属性やcolor属性からRGB値を返す"""
    if not style_str:
        return None
    
    # 1. Hexコード (#FF0000) を探す
    hex_match = re.search(r'#([0-9a-fA-F]{6})', style_str)
    if hex_match:
        hex_code = hex_match.group(1)
        return RGBColor(int(hex_code[:2], 16), int(hex_code[2:4], 16), int(hex_code[4:], 16))
    
    # 2. 一般的な色名を探す（h-kenでよく使われる色）
    style_lower = style_str.lower()
    colors = {
        'red': RGBColor(255, 0, 0),
        'blue': RGBColor(0, 0, 255),
        'green': RGBColor(0, 128, 0),
        'lightseagreen': RGBColor(32, 178, 170), # タイトルによくある色
        'pink': RGBColor(255, 192, 203),
        'orange': RGBColor(255, 165, 0),
        'purple': RGBColor(128, 0, 128),
        'gray': RGBColor(128, 128, 128),
        'grey': RGBColor(128, 128, 128),
        'bold': None # 色ではないがスタイルにある場合
    }
    
    for name, rgb in colors.items():
        if name in style_lower:
            return rgb
            
    return None

def apply_html_style_to_run(run, tag):
    """HTMLタグのスタイル（太字、色）をWordのRunに適用する"""
    # 太字判定
    style_attr = tag.get('style', '').lower()
    if tag.name in ['b', 'strong'] or 'font-weight:bold' in style_attr or 'font-weight: bold' in style_attr:
        run.bold = True
    
    # 色判定 (style="color:..." または <font color="...">)
    color = None
    if 'color' in style_attr:
        color = parse_color(style_attr)
    elif tag.get('color'):
        color = parse_color(tag.get('color'))
        
    if color:
        run.font.color.rgb = color

def process_element_to_docx(paragraph, element):
    """HTML要素を再帰的に解析してWordに追加する"""
    if isinstance(element, NavigableString):
        text = str(element)
        if text.strip(): # 空白だけの場合は無視するか、そのまま入れるか
            paragraph.add_run(text)
    
    elif isinstance(element, Tag):
        # 改行タグ
        if element.name == 'br':
            paragraph.add_run('\n')
        
        # コンテナタグの場合は中身を掘り下げる
        elif element.name in ['span', 'font', 'b', 'strong', 'i', 'em', 'a']:
            # このタグの中身をすべて取得
            for child in element.children:
                if isinstance(child, NavigableString):
                    run = paragraph.add_run(str(child))
                    apply_html_style_to_run(run, element)
                elif isinstance(child, Tag):
                    # ネストしている場合（<span><b>文字</b></span>など）
                    # 再帰呼び出ししたいが、簡易的にスタイルを継承させる
                    # 今回は「親のスタイル」を適用しつつ中身を追加
                    process_element_to_docx(paragraph, child)
                    # 注意: 厳密な継承は複雑になるため、直近のタグのスタイルを優先
        
        else:
            # その他のタグは中身だけ展開
            for child in element.children:
                process_element_to_docx(paragraph, child)

# ==========================================
# Wordファイル作成（リッチテキスト対応版）
# ==========================================
def create_rich_docx(title_html, body_html):
    doc = Document()
    
    # --- タイトルの処理 ---
    # HTML解析
    soup_title = BeautifulSoup(title_html, 'html.parser')
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    # タイトルのスタイル適用（h1の中身を解析）
    if soup_title.h1:
        # H1タグそのもののスタイル
        h1_tag = soup_title.h1
        for child in h1_tag.children:
            if isinstance(child, NavigableString):
                run = p_title.add_run(str(child))
                run.font.size = Pt(16)
                run.bold = True
            elif isinstance(child, Tag):
                run = p_title.add_run(child.get_text())
                run.font.size = Pt(16)
                apply_html_style_to_run(run, child)
    else:
        # HTMLでなければそのままテキスト追加
        p_title.add_run(soup_title.get_text()).font.size = Pt(16)

    doc.add_paragraph("") # 空行

    # --- 本文の処理 ---
    soup_body = BeautifulSoup(body_html, 'html.parser')
    
    # ブロック要素ごとに段落を作る
    # div, p, h2, h3 などを段落とみなす
    blocks = soup_body.find_all(['p', 'div', 'h2', 'h3'], recursive=True)
    
    # もしfind_allでうまく階層が取れない場合、ルート直下を見る
    if not blocks:
        top_elements = soup_body.find_all(True, recursive=False)
        blocks = top_elements if top_elements else [soup_body]

    for block in blocks:
        # ブロック内のテキストが空でなければ段落追加
        if block.get_text(strip=True):
            p = doc.add_paragraph()
            process_element_to_docx(p, block)
            
    buffer = BytesIO()
    doc.save(buffer)
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
    target_h1 = soup.find("h1", class_="pageTitle")
    if target_h1:
        title_html = str(target_h1)
    else:
        target_h1 = soup.find("h1")
        if target_h1:
            title_html = str(target_h1)

    # 本文
    body_html = "<div>本文が見つかりませんでした</div>"
    
    target_div = soup.find(id="sentenceBox")
    if not target_div:
        target_div = soup.find(id="main_txt")

    if target_div:
        # ゴミ掃除
        for bad in target_div.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
            bad.decompose()

        # 文末カット
        cut_point = target_div.find(class_="kakomiPop2")
        if cut_point:
            for sibling in cut_point.find_next_siblings():
                sibling.decompose()
            cut_point.decompose()

        body_html = str(target_div)

    # HTMLプレビュー作成
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

    # ここではHTML文字列そのものを返す（Word作成関数側でパースする）
    return title_html, body_html, final_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Pro", layout="centered")

st.title("💎 色付きWord保存アプリ")
st.caption("サイトの赤文字や強調をWordにそのまま保存します。")

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
            
            # 抽出
            title_html_str, body_html_str, final_html_preview = extract_target_content(html, url)
            
            status.empty()
            st.success("抽出完了！")
            
            # --- 保存ボタンエリア ---
            # 今回はWordに特化します（PDFはWordから保存してもらう方が確実なため）
            
            # 色付きWordを作成
            docx_file = create_rich_docx(title_html_str, body_html_str)
            
            st.download_button(
                label="📘 Word(.docx) で色付き保存",
                data=docx_file,
                file_name="story_colored.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            
            st.info("💡 PDFが必要な場合は、保存したWordを開き「名前を付けて保存」からPDFを選んでください。文字化けせず一番きれいに保存できます。")

            st.divider()
            
            # プレビュー
            components.html(final_html_preview, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
