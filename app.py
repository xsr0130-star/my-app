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
# 【修正】色解析ロジック（Hex, RGB, 色名対応）
# ==========================================
def get_rgb_from_str(color_str):
    """文字列（red, #ff0000等）からRGBColorオブジェクトを返す"""
    if not color_str:
        return None
    
    color_str = color_str.lower().strip()
    
    # 1. Hex (#RRGGBB)
    hex_match = re.search(r'#([0-9a-f]{6})', color_str)
    if hex_match:
        h = hex_match.group(1)
        return RGBColor(int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16))
    
    # 2. 色名マップ（サイトで使われそうな色）
    colors = {
        'red': RGBColor(255, 0, 0),
        'blue': RGBColor(0, 0, 255),
        'green': RGBColor(0, 128, 0),
        'lightseagreen': RGBColor(32, 178, 170), # タイトルの色
        'pink': RGBColor(255, 192, 203),
        'orange': RGBColor(255, 165, 0),
        'purple': RGBColor(128, 0, 128),
        'gray': RGBColor(128, 128, 128),
        'grey': RGBColor(128, 128, 128),
        'black': RGBColor(0, 0, 0),
        'white': RGBColor(255, 255, 255)
    }
    
    return colors.get(color_str)

def apply_styles_recursive(run, element):
    """
    文字(NavigableString)から親タグを遡ってスタイル（色・太字）を探し、
    WordのRunに適用する
    """
    # 親、その親、さらにその親...と3階層くらい遡ってスタイルを探す
    # 例: <span style="color:red"><b>文字</b></span> の場合、bには色がないがspanにある
    
    current = element.parent
    font_color_set = False
    bold_set = False
    
    # 最大3階層さかのぼる
    for _ in range(3):
        if not current or current.name in ['div', 'p', 'body', 'html', '[document]']:
            break
        
        # スタイル属性を取得
        style_attr = current.get('style', '').lower()
        tag_name = current.name
        
        # --- 太字判定 ---
        if not bold_set:
            if tag_name in ['b', 'strong'] or 'font-weight:bold' in style_attr or 'font-weight: bold' in style_attr:
                run.bold = True
                bold_set = True

        # --- 色判定 ---
        if not font_color_set:
            color_val = None
            
            # 1. <font color="...">
            if current.get('color'):
                color_val = current.get('color')
            
            # 2. style="color: ..."
            elif 'color' in style_attr:
                # 正規表現で color: の後ろの値を取り出す
                m = re.search(r'color\s*:\s*([^;"]+)', style_attr)
                if m:
                    color_val = m.group(1)
            
            if color_val:
                rgb = get_rgb_from_str(color_val)
                if rgb:
                    run.font.color.rgb = rgb
                    font_color_set = True
        
        current = current.parent

# ==========================================
# Word作成エンジン（再帰処理）
# ==========================================
def add_html_elements_to_paragraph(paragraph, soup_element):
    """HTML要素を解析してWord段落に追加する（再帰）"""
    for child in soup_element.children:
        if isinstance(child, NavigableString):
            text = str(child)
            # 改行コードは除去せず、Word側で制御
            if text:
                run = paragraph.add_run(text)
                # ここで親タグを遡ってスタイルを適用
                apply_styles_recursive(run, child)
                
        elif isinstance(child, Tag):
            if child.name == 'br':
                paragraph.add_run('\n')
            else:
                # さらに中身を掘り下げる
                add_html_elements_to_paragraph(paragraph, child)

def create_rich_docx(title_html, body_html):
    doc = Document()
    
    # --- タイトル ---
    soup_title = BeautifulSoup(title_html, 'html.parser')
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    # タイトル内の解析
    if soup_title.h1:
        add_html_elements_to_paragraph(p_title, soup_title.h1)
    else:
        # H1がない場合
        run = p_title.add_run(soup_title.get_text())
    
    # タイトル全体を大きく
    for run in p_title.runs:
        run.font.size = Pt(16)
        if not run.bold: run.bold = True # タイトルは強制太字

    doc.add_paragraph("") # 空行

    # --- 本文 ---
    soup_body = BeautifulSoup(body_html, 'html.parser')
    
    # ブロック要素ごとに段落を分ける
    # div, p, h2~h6
    blocks = soup_body.find_all(['div', 'p', 'h2', 'h3', 'h4', 'blockquote'], recursive=False)
    
    # ルート直下にテキストがある場合の対応
    if not blocks:
        # 再帰的に探すのではなく、このdivそのものを1つのブロックとして扱う
        p = doc.add_paragraph()
        add_html_elements_to_paragraph(p, soup_body)
    else:
        for block in blocks:
            # テキストが含まれているか確認
            if block.get_text(strip=True):
                p = doc.add_paragraph()
                add_html_elements_to_paragraph(p, block)
    
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
# 抽出ロジック（警告削除機能追加）
# ==========================================
def extract_target_content(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # CSS確保
    styles = []
    for link in soup.find_all('link', rel='stylesheet'):
        styles.append(str(link))
    for style in soup.find_all('style'):
        styles.append(str(style))
    style_html = "\n".join(styles)

    # タイトル抽出
    title_html = ""
    target_h1 = soup.find("h1", class_="pageTitle")
    if target_h1:
        title_html = str(target_h1)
    else:
        target_h1 = soup.find("h1")
        if target_h1:
            title_html = str(target_h1)

    # 本文抽出
    body_html = "<div>本文が見つかりませんでした</div>"
    
    target_div = soup.find(id="sentenceBox")
    if not target_div:
        target_div = soup.find(id="main_txt")

    if target_div:
        # 1. 基本的なゴミ掃除
        for bad in target_div.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
            bad.decompose()

        # 2. 文末カット（kakomiPop2以降）
        cut_point = target_div.find(class_="kakomiPop2")
        if cut_point:
            for sibling in cut_point.find_next_siblings():
                sibling.decompose()
            cut_point.decompose()

        # 3. 【追加】不要な警告文（著作権など）の削除
        # "無断転載はご遠慮願います" を含む pタグや divタグを探して消す
        for tag in target_div.find_all(['p', 'div', 'span']):
            text = tag.get_text()
            if "無断転載はご遠慮願います" in text or "Googleに通報します" in text or "エチケン" in text:
                # 本文ごと消えないように、文字数が極端に多い場合は消さない（警告文は通常短い）
                if len(text) < 300: 
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

    return title_html, body_html, final_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Pro", layout="centered")

st.title("💎 色付きWord保存アプリ")
st.caption("不要な警告文を削除し、色を維持してWord化します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出を開始する", type="primary", use_container_width=True):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.info("⏳ サイトを解析中... (10〜20秒かかります)")
        
        html = fetch_html_force_clean(url)

        if html:
            status.info("📄 データ生成中...")
            
            # 抽出処理
            title_html_str, body_html_str, final_html_preview = extract_target_content(html, url)
            
            status.empty()
            st.success("抽出完了！")
            
            # 色付きWordを作成
            docx_file = create_rich_docx(title_html_str, body_html_str)
            
            st.download_button(
                label="📘 Word(.docx) で色付き保存",
                data=docx_file,
                file_name="story_colored.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            
            st.info("💡 Wordを開き「PDFとして保存」すると、きれいにPDF化できます。")

            st.divider()
            
            # プレビュー表示
            components.html(final_html_preview, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
