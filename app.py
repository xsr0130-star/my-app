import streamlit as st
import streamlit.components.v1 as components  # ← これが重要：HTML表示用の部品
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import subprocess

# ==========================================
# 設定：入り口となるURL
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
# ブラウザ操作
# ==========================================
def fetch_html_via_route(target_url):
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
            time.sleep(3) 

            # 2. 目的のURLへ
            page.goto(target_url, timeout=30000)
            page.wait_for_load_state("networkidle")

            return page.content()

        except Exception as e:
            st.error(f"エラー: {e}")
            return None
        finally:
            browser.close()

# ==========================================
# 抽出ロジック（色付き重視）
# ==========================================
def extract_colored_body(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 不要なタグ削除（色は残すため、fontやspanは消さない）
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "form", "button", "input", "meta", "link", "img", "svg"]):
        tag.decompose()

    # タイトル
    title_text = "タイトルなし"
    h1 = soup.find('h1')
    if h1:
        title_text = h1.get_text(strip=True)
    elif soup.title:
        title_text = soup.title.get_text(strip=True)

    # 本文（HTML保持）
    max_score = 0
    best_html = "<div>本文が見つかりませんでした</div>"
    
    candidates = soup.find_all(['div', 'article', 'section', 'main'])

    for candidate in candidates:
        text = candidate.get_text(strip=True)
        score = len(text)
        
        # リンク文字率が高いブロックを除外
        links = candidate.find_all('a')
        link_len = sum([len(a.get_text()) for a in links])
        if score > 0 and (link_len / score) > 0.5:
            continue

        if score > max_score:
            max_score = score
            # ここでHTMLタグごと取得する
            best_html = str(candidate)

    return title_text, best_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="Review Extractor", layout="centered")
st.title("🌈 完全色付き抽出アプリ")
st.caption("サイトのデザイン（色・太字）をそのまま表示します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出開始"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("読み込み中...")
        
        html = fetch_html_via_route(url)

        if html:
            title, body_html = extract_colored_body(html)
            status.empty()
            
            st.success("完了")
            st.subheader(title)
            st.divider()
            
            # 【ここが変更点】
            # HTMLを見やすくするためのCSSを追加して、iframeの中に表示します
            custom_css = """
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #fff;
                    padding: 10px;
                }
                /* 強調色の補正 */
                .red, .danger, .marker { color: red !important; font-weight: bold; }
            </style>
            """
            
            # 抽出したHTMLにCSSをくっつける
            final_html = custom_css + body_html
            
            # iframeとして表示（これで色が守られます）
            components.html(final_html, height=600, scrolling=True)
            
            st.divider()
        else:
            status.error("失敗しました。")
