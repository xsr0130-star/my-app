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
# 色解析ロジック（CSSクラス対応版）
# ==========================================
def get_rgb_from_str(color_str):
    """色文字列からRGBColorを返す"""
    if not color_str: return None
    c = color_str.lower().strip()
    
    # Hex
    hex_match = re.search(r'#([0-9a-f]{6})', c)
    if hex_match:
        h = hex_match.group(1)
        return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16))
    
    # 基本色マップ
    colors = {
        'red': RGBColor(255, 0, 0),
        'blue': RGBColor(0, 0, 255),
        'green': RGBColor(0, 128, 0),
        'lightseagreen': RGBColor(32, 178, 170),
        'pink': RGBColor(255, 192, 203),
        'orange': RGBColor(255, 165, 0),
        'purple': RGBColor(128, 0, 128),
        'gray': RGBColor(128, 128, 128),
        'black': RGBColor(0, 0, 0)
    }
    return colors.get(c.split()[0]) # "red !important" 対策

def parse_css_colors(soup):
    """<style>タグを解析して {クラス名: RGBColor} の辞書を作る"""
    css_map = {}
    
    # ページ内の全styleタグを走査
    for style in soup.find_all('style'):
        if style.string:
            # 正規表現で .classname { color: #xxx; } を探す
            # 簡易的なパースなので完全ではないが、主要なものは拾える
            matches = re.finditer(r'\.([a-zA-Z0-9_-]+)\s*\{[^}]*color\s*:\s*([^;\}]+)', style.string, re.IGNORECASE)
            for m in matches:
                class_name = m.group(1)
                color_val = m.group(2).strip()
                rgb = get_rgb_from_str(color_val)
                if rgb:
                    css_map[class_name] = rgb
                    
    # よくある固定クラスも追加しておく
    css_map['conversation'] = RGBColor(255, 0, 0) # 仮に赤とする（必要なら変更可）
    css_map['red'] = RGBColor(255, 0, 0)
    css_map['blue'] = RGBColor(0, 0, 255)
    css_map['marker'] = RGBColor(255, 0, 0) # マーカーは大抵赤か黄色
    
    return css_map

def apply_style_to_run(run, element, css_map):
    """要素のstyle属性やclass属性を見てWordのRunに色・太字を適用"""
    
    # 1. 太字判定
    style_attr = element.get('style', '').lower()
    classes = element.get('class', [])
    
    if element.name in ['b', 'strong', 'h1', 'h2'] or \
       'font-weight:bold' in style_attr or 'font-weight: bold' in style_attr or \
       'bold' in classes:
        run.bold = True
        
    # 2. 色判定（優先順位: style属性 > class属性 > fontタグ）
    rgb = None
    
    # A. style="color:..."
    if 'color' in style_attr:
        m = re.search(r'color\s*:\s*([^;"]+)', style_attr)
        if m:
            rgb = get_rgb_from_str(m.group(1))
            
    # B. class="..." (CSSマップから検索)
    if not rgb and classes:
        for cls in classes:
            if cls in css_map:
                rgb = css_map[cls]
                break
                
    # C. <font color="...">
    if not rgb and element.get('color'):
        rgb = get_rgb_from_str(element.get('color'))

    if rgb:
        run.font.color.rgb = rgb

# ==========================================
# Word作成エンジン
# ==========================================
def process_node_recursive(paragraph, node, css_map):
    """再帰的にノードを処理してWordに追加"""
    if isinstance(node, NavigableString):
        text = str(node)
        # 不要なコメント文字列等が残っていないか最終チェック
        if "contents_within" not in text and text.strip():
            run = paragraph.add_run(text)
            # 親タグのスタイルを探して適用（直近の親のみ簡易適用）
            if node.parent:
                apply_style_to_run(run, node.parent, css_map)
                
    elif isinstance(node, Tag):
        if node.name == 'br':
            paragraph.add_run('\n')
        elif node.name in ['script', 'style', 'noscript']:
            pass # 無視
        else:
            # 子要素を再帰処理
            for child in node.children:
                process_node_recursive(paragraph, child, css_map)

def create_rich_docx(title_html, body_html, css_map):
    doc = Document()
    
    # タイトル
    soup_title = BeautifulSoup(title_html, 'html.parser')
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    process_node_recursive(p_title, soup_title, css_map)
    
    # タイトル全体を強調
    for run in p_title.runs:
        run.font.size = Pt(16)
        if not run.bold: run.bold = True

    doc.add_paragraph("") 

    # 本文
    soup_body = BeautifulSoup(body_html, 'html.parser')
    # ブロック要素ごとに段落分け
    blocks = soup_body.find_all(['p', 'div', 'h2', 'h3', 'blockquote'], recursive=False)
    if not blocks:
        # ルート直下の場合
        p = doc.add_paragraph()
        process_node_recursive(p, soup_body, css_map)
    else:
        for block in blocks:
            if block.get_text(strip=True):
                p = doc.add_paragraph()
                process_node_recursive(p, block, css_map)
    
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
# 抽出＆クリーニングロジック（強化版）
# ==========================================
def extract_target_content(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. CSS解析（Word用）
    css_map = parse_css_colors(soup)
    
    # 2. 表示用スタイル確保
    styles = []
    for link in soup.find_all('link', rel='stylesheet'):
        styles.append(str(link))
    for style in soup.find_all('style'):
        styles.append(str(style))
    style_html = "\n".join(styles)

    # 3. タイトル抽出
    title_html = ""
    target_h1 = soup.find("h1", class_="pageTitle")
    if target_h1:
        title_html = str(target_h1)
    else:
        target_h1 = soup.find("h1")
        if target_h1:
            title_html = str(target_h1)

    # 4. 本文抽出
    body_html = "<div>本文が見つかりませんでした</div>"
    
    target_div = soup.find(id="sentenceBox")
    if not target_div:
        target_div = soup.find(id="main_txt")

    if target_div:
        # --- A. HTMLコメント（<!-- -->）の完全削除 ---
        for comment in target_div.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
            
        # --- B. 不要タグ削除 ---
        for bad in target_div.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
            bad.decompose()

        # --- C. 文末カット ---
        cut_point = target_div.find(class_="kakomiPop2")
        if cut_point:
            for sibling in cut_point.find_next_siblings():
                sibling.decompose()
            cut_point.decompose()

        # --- D. 警告文・不要テキストの強力削除 ---
        # 削除したいキーワードリスト
        bad_words = [
            "無断転載", "Googleに通報", "刑事告訴", "民事訴訟", "エチケン", 
            "contents_within", "!--"
        ]
        
        # テキストを含む要素を探して削除
        # 範囲を広げて p, div, span, font などを見る
        for tag in target_div.find_all(['p', 'div', 'span', 'font', 'b']):
            text = tag.get_text()
            # キーワードが含まれていて、かつ本文（長文）ではない場合
            if any(w in text for w in bad_words):
                if len(text) < 400: # 400文字以下の警告ブロックなら削除
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
st.caption("警告文削除・色付きWord保存対応")

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
            
            # 抽出（css_mapも受け取る）
            title_html_str, body_html_str, final_html_preview, css_map = extract_target_content(html, url)
            
            status.empty()
            st.success("完了！")
            
            # 色付きWordを作成（css_mapを渡す）
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
