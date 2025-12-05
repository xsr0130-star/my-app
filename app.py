import streamlit as st
import streamlit.components.v1 as components
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, NavigableString, Tag, Comment
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
# 設定
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
# 【強化】色解析ロジック（多色・RGB対応）
# ==========================================
def get_rgb_from_str(color_str):
    """
    あらゆる色指定文字列からRGBColorオブジェクトを返す
    対応: 色名(red, hotpink...), Hex(#FFF, #FFFFFF), rgb(r,g,b)
    """
    if not color_str: return None
    
    # 小文字化 & 不要な !important などを削除
    c = color_str.lower().strip().replace('!important', '').strip()
    
    # 1. Hex 6桁 (#RRGGBB)
    hex_match = re.search(r'#([0-9a-f]{6})', c)
    if hex_match:
        h = hex_match.group(1)
        return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16))
        
    # 2. Hex 3桁 (#RGB) -> #RRGGBB に変換
    hex_match_short = re.search(r'#([0-9a-f]{3})\b', c)
    if hex_match_short:
        h = hex_match_short.group(1)
        return RGBColor(int(h[0]*2, 16), int(h[1]*2, 16), int(h[2]*2, 16))
        
    # 3. rgb(r, g, b) 表記
    rgb_match = re.search(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', c)
    if rgb_match:
        return RGBColor(int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3)))

    # 4. 拡張色名マップ（Web標準色を網羅）
    colors = {
        # 基本色
        'red': RGBColor(255, 0, 0), 'blue': RGBColor(0, 0, 255), 'green': RGBColor(0, 128, 0),
        'black': RGBColor(0, 0, 0), 'white': RGBColor(255, 255, 255),
        'gray': RGBColor(128, 128, 128), 'grey': RGBColor(128, 128, 128),
        # サイトでよく使われる色
        'lightseagreen': RGBColor(32, 178, 170),
        'orange': RGBColor(255, 165, 0), 'darkorange': RGBColor(255, 140, 0), 'orangered': RGBColor(255, 69, 0),
        'pink': RGBColor(255, 192, 203), 'lightpink': RGBColor(255, 182, 193), 'hotpink': RGBColor(255, 105, 180), 'deeppink': RGBColor(255, 20, 147),
        'purple': RGBColor(128, 0, 128), 'violet': RGBColor(238, 130, 238), 'magenta': RGBColor(255, 0, 255), 'fuchsia': RGBColor(255, 0, 255),
        'cyan': RGBColor(0, 255, 255), 'aqua': RGBColor(0, 255, 255),
        'yellow': RGBColor(255, 255, 0), 'gold': RGBColor(255, 215, 0),
        'brown': RGBColor(165, 42, 42), 'maroon': RGBColor(128, 0, 0),
        'lime': RGBColor(0, 255, 0), 'limegreen': RGBColor(50, 205, 50),
        'navy': RGBColor(0, 0, 128), 'teal': RGBColor(0, 128, 128),
        'silver': RGBColor(192, 192, 192),
    }
    
    return colors.get(c)

def parse_css_colors(soup):
    """CSS内のクラス定義から色を抽出"""
    css_map = {}
    for style in soup.find_all('style'):
        if style.string:
            # .classname { color: red; } を抽出
            matches = re.finditer(r'\.([a-zA-Z0-9_-]+)\s*\{[^}]*color\s*:\s*([^;\}]+)', style.string, re.IGNORECASE)
            for m in matches:
                class_name = m.group(1)
                color_val = m.group(2).strip()
                rgb = get_rgb_from_str(color_val)
                if rgb:
                    css_map[class_name] = rgb
                    
    # よくある固定クラスのデフォルト値
    defaults = {
        'conversation': RGBColor(255, 0, 0), # デフォルト赤
        'marker': RGBColor(255, 0, 0),
        'red': RGBColor(255, 0, 0),
        'blue': RGBColor(0, 0, 255),
        'pink': RGBColor(255, 105, 180)
    }
    for k, v in defaults.items():
        if k not in css_map:
            css_map[k] = v
            
    return css_map

def apply_style_to_run(run, element, css_map):
    """WordのRunにスタイルを適用（多色対応）"""
    style_attr = element.get('style', '').lower()
    classes = element.get('class', [])
    
    # 太字
    if element.name in ['b', 'strong', 'h1', 'h2'] or 'font-weight:bold' in style_attr or 'bold' in classes:
        run.bold = True
        
    # 色判定
    rgb = None
    
    # 1. style="color: ..."
    if 'color' in style_attr:
        # color: xxx; の xxx を取り出す
        m = re.search(r'color\s*:\s*([^;"]+)', style_attr)
        if m: rgb = get_rgb_from_str(m.group(1))
    
    # 2. class="..."
    if not rgb and classes:
        for cls in classes:
            if cls in css_map:
                rgb = css_map[cls]
                break
                
    # 3. <font color="...">
    if not rgb and element.get('color'):
        rgb = get_rgb_from_str(element.get('color'))

    if rgb:
        run.font.color.rgb = rgb

# ==========================================
# Word作成エンジン（改行対応）
# ==========================================
BLOCK_TAGS = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'li', 'article', 'section']

def process_node_recursive(paragraph, node, css_map):
    """再帰的にノードを処理"""
    if isinstance(node, NavigableString):
        text = str(node)
        if "contents_within" not in text and text.strip():
            run = paragraph.add_run(text)
            if node.parent:
                apply_style_to_run(run, node.parent, css_map)
                
    elif isinstance(node, Tag):
        if node.name == 'br':
            paragraph.add_run('\n')
        elif node.name in ['script', 'style', 'noscript']:
            pass
        else:
            for child in node.children:
                process_node_recursive(paragraph, child, css_map)
            
            # ブロック要素の終わりで改行
            if node.name in BLOCK_TAGS:
                paragraph.add_run('\n')

def create_rich_docx(title_html, body_html, css_map):
    doc = Document()
    
    # タイトル
    soup_title = BeautifulSoup(title_html, 'html.parser')
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    process_node_recursive(p_title, soup_title, css_map)
    
    for run in p_title.runs:
        run.font.size = Pt(16)
        if not run.bold: run.bold = True

    doc.add_paragraph("") 

    # 本文
    soup_body = BeautifulSoup(body_html, 'html.parser')
    
    # ルート直下の要素ごとに段落作成
    top_level_elements = soup_body.find_all(True, recursive=False)
    
    if not top_level_elements:
        p = doc.add_paragraph()
        process_node_recursive(p, soup_body, css_map)
    else:
        for element in top_level_elements:
            p = doc.add_paragraph()
            process_node_recursive(p, element, css_map)
    
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

            # ポップアップ破壊JS
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
# 抽出ロジック（警告削除・文末カット）
# ==========================================
def extract_target_content(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    css_map = parse_css_colors(soup)
    
    styles = []
    for link in soup.find_all('link', rel='stylesheet'):
        styles.append(str(link))
    for style in soup.find_all('style'):
        styles.append(str(style))
    style_html = "\n".join(styles)

    title_html = ""
    target_h1 = soup.find("h1", class_="pageTitle")
    if target_h1:
        title_html = str(target_h1)
    else:
        target_h1 = soup.find("h1")
        if target_h1:
            title_html = str(target_h1)

    body_html = "<div>本文が見つかりませんでした</div>"
    target_div = soup.find(id="sentenceBox")
    if not target_div:
        target_div = soup.find(id="main_txt")

    if target_div:
        # コメント削除
        for comment in target_div.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
            
        # 不要タグ削除
        for bad in target_div.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
            bad.decompose()

        # 文末カット
        cut_point = target_div.find(class_="kakomiPop2")
        if cut_point:
            for sibling in cut_point.find_next_siblings():
                sibling.decompose()
            cut_point.decompose()

        # 警告文削除
        bad_words = ["無断転載", "Googleに通報", "刑事告訴", "民事訴訟", "エチケン", "contents_within"]
        for tag in target_div.find_all(['p', 'div', 'span', 'font', 'b']):
            text = tag.get_text()
            if any(w in text for w in bad_words):
                if len(text) < 400:
                    tag.decompose()

        body_html = str(target_div)

    # HTMLプレビュー
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

    return title_html, body_html, final_html, css_map

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Final", layout="centered")

st.title("💎 完成版コンテンツ抽出")
st.caption("警告削除・改行・多色対応")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出を開始する", type="primary", use_container_width=True):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.info("⏳ 解析中...")
        
        html = fetch_html_force_clean(url)

        if html:
            status.info("📄 データ生成中...")
            
            title_html_str, body_html_str, final_html_preview, css_map = extract_target_content(html, url)
            
            status.empty()
            st.success("完了！")
            
            docx_file = create_rich_docx(title_html_str, body_html_str, css_map)
            
            st.download_button(
                label="📘 Word(.docx) で保存",
                data=docx_file,
                file_name="story_colored.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            
            st.divider()
            components.html(final_html_preview, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
