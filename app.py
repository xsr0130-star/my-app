import streamlit as st
import streamlit.components.v1 as components
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
# 抽出ロジック（CSSリンク完全保持版）
# ==========================================
def extract_with_css(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. デザインに関わるタグ（link, style）をすべて抽出して保存しておく
    # これがないと class="conversation" の色が分かりません
    head_styles = []
    
    # 外部CSSファイルへのリンクを取得
    for link in soup.find_all('link', rel='stylesheet'):
        head_styles.append(str(link))
        
    # ページ内に直接書かれたスタイルを取得
    for style in soup.find_all('style'):
        head_styles.append(str(style))
        
    # スタイル群を結合
    styles_html = "\n".join(head_styles)

    # 2. 不要な要素の削除（scriptなどは消すが、デザイン系は残す）
    for tag in soup(["script", "noscript", "iframe", "form", "button", "input", "img", "svg"]):
        tag.decompose()

    # 3. タイトル取得
    title_text = "タイトルなし"
    h1 = soup.find('h1')
    if h1:
        title_text = h1.get_text(strip=True)
    elif soup.title:
        title_text = soup.title.get_text(strip=True)

    # 4. 本文抽出
    max_score = 0
    best_body_html = "<div>本文が見つかりませんでした</div>"
    
    candidates = soup.find_all(['div', 'article', 'section', 'main'])

    for candidate in candidates:
        text = candidate.get_text(strip=True)
        score = len(text)
        
        # リンク文字率が高いブロック（メニュー等）を除外
        links = candidate.find_all('a')
        link_len = sum([len(a.get_text()) for a in links])
        if score > 0 and (link_len / score) > 0.5:
            continue

        if score > max_score:
            max_score = score
            best_body_html = str(candidate)

    # 5. 最終的なHTMLを組み立てる
    # ここが重要： <base href="..."> を入れることで、相対パスのCSSを読み込めるようにする
    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <base href="{target_url}"> <!-- これで外部CSSファイルが読み込まれます -->
        {styles_html} <!-- 元サイトのデザインルールを注入 -->
        <style>
            body {{
                background-color: #fff;
                padding: 20px;
                font-family: sans-serif;
            }}
            /* 画像を消した跡地が崩れないように調整 */
            img {{ display: none !important; }}
        </style>
    </head>
    <body>
        {best_body_html}
    </body>
    </html>
    """

    return title_text, final_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Pro", layout="centered")
st.title("🌈 デザイン完全再現アプリ")
st.caption("CSSクラス（conversation等）も反映して表示します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出開始"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("読み込み中...")
        
        html = fetch_html_via_route(url)

        if html:
            # URLも渡す（Base URL設定のため）
            title, final_html = extract_with_css(html, url)
            
            status.empty()
            
            st.success("完了")
            st.subheader(title)
            st.divider()
            
            # iframeで表示（外部CSSを読み込ませるため）
            components.html(final_html, height=800, scrolling=True)
            
            st.divider()
        else:
            status.error("失敗しました。")
