import streamlit as st
import streamlit.components.v1 as components
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import subprocess

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
# ブラウザ操作（JSでポップアップ破壊）
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
            # 1. 入り口URLへ
            page.goto(FIXED_ENTRY_URL, timeout=30000)
            time.sleep(2) 

            # 2. 目的のURLへ
            page.goto(target_url, timeout=30000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2) 

            # 3. ポップアップ破壊＆年齢確認クリック
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
# 抽出ロジック（kakomiPop2以降カット機能追加）
# ==========================================
def extract_target_content(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. CSS確保
    styles = []
    for link in soup.find_all('link', rel='stylesheet'):
        styles.append(str(link))
    for style in soup.find_all('style'):
        styles.append(str(style))
    style_html = "\n".join(styles)

    # -------------------------------------------------
    # 2. タイトルの抽出
    # -------------------------------------------------
    title_html = ""
    target_h1 = soup.find("h1", class_="pageTitle")
    if target_h1:
        title_html = str(target_h1)
    else:
        target_h1 = soup.find("h1")
        if target_h1:
            title_html = str(target_h1)

    simple_title_text = soup.title.get_text(strip=True) if soup.title else "抽出結果"

    # -------------------------------------------------
    # 3. 本文の抽出 & 不要部分のカット
    # -------------------------------------------------
    body_html = "<div>本文が見つかりませんでした</div>"
    target_div = soup.find(id="sentenceBox")

    if not target_div:
        target_div = soup.find(id="main_txt")

    if target_div:
        # (A) 基本的なゴミ掃除
        for bad in target_div.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
            bad.decompose()

        # (B) 【追加機能】kakomiPop2 を見つけたら、そこから下を全削除
        # class="kakomiPop2" を持つ要素を探す
        cut_point = target_div.find(class_="kakomiPop2")
        
        if cut_point:
            # その要素より後ろにある兄弟要素（弟たち）をすべて削除
            for sibling in cut_point.find_next_siblings():
                sibling.decompose()
            # その要素自身（kakomiPop2）も削除
            cut_point.decompose()

        # HTMLとして取得
        body_html = str(target_div)

    # -------------------------------------------------
    # 4. 合体
    # -------------------------------------------------
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
            /* タイトル調整 */
            h1.pageTitle {{
                font-size: 20px;
                margin-bottom: 20px;
                border-bottom: 1px solid #ccc;
                padding-bottom: 10px;
                line-height: 1.4;
            }}
            /* 本文調整 */
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

    return simple_title_text, final_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Master", layout="centered")
st.title("✂️ 文末カット対応リーダー")
st.caption("「この話の続き」などの不要なリンク集を自動で削除します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出する"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("読み込み中...")
        
        html = fetch_html_force_clean(url)

        if html:
            status.text("不要ブロックをカット中...")
            simple_title, final_html = extract_target_content(html, url)
            status.empty()
            
            st.success("完了")
            
            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
