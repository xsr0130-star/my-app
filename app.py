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
# 抽出ロジック（引き算方式）
# ==========================================
def clean_html_keep_css(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. <base>タグを追加して、CSSや画像のリンク切れを防ぐ
    # 既存のheadを取得、なければ作る
    if not soup.head:
        new_head = soup.new_tag("head")
        soup.insert(0, new_head)
    
    # baseタグをheadの先頭に追加
    base_tag = soup.new_tag("base", href=target_url)
    if soup.head.base:
        soup.head.base.replace_with(base_tag)
    else:
        soup.head.insert(0, base_tag)

    # 2. 明らかに不要なタグだけをピンポイントで削除（引き算）
    # 本文が含まれる可能性がある div や table は消さない！
    garbage_tags = [
        "script",     # プログラム
        "noscript",   # プログラムなし用表示
        "iframe",     # 外部埋め込み（広告など）
        "form",       # 入力フォーム
        "button",     # ボタン
        "input",      # 入力欄
        "nav",        # ナビゲーションメニュー
        "footer",     # フッター（著作権表示など）
        "header",     # ヘッダー（ロゴなど）
    ]
    
    for tag_name in garbage_tags:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 3. 画像を表示するかどうか（今回は「文字だけ見たい」要望に合わせて非表示にするCSSを追加）
    # 画像も見たければ、以下の style タグの img 部分を消してください
    custom_style = soup.new_tag("style")
    custom_style.string = """
        body { background-color: #fff !important; font-family: sans-serif; }
        /* 画像を非表示にする（レイアウト崩れ防止のため display:none 推奨） */
        img { display: none !important; }
        /* 画面幅をスマホっぽく調整 */
        .wrapper, #wrapper, .container { width: 100% !important; max-width: 100% !important; }
    """
    soup.head.append(custom_style)

    # 4. タイトル取得（表示用）
    title_text = "タイトルなし"
    if soup.title:
        title_text = soup.title.get_text(strip=True)

    # 5. 整形したHTML全体を文字列にする
    cleaned_html = str(soup)

    return title_text, cleaned_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Cleaner", layout="centered")
st.title("🧹 サイトお掃除リーダー")
st.caption("CSSや色はそのままに、広告やメニューだけ取り除きます。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("表示する"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("サイトにアクセス中...")
        
        html = fetch_html_via_route(url)

        if html:
            status.text("不要なデータを掃除中...")
            title, final_html = clean_html_keep_css(html, url)
            status.empty()
            
            st.success("完了")
            st.subheader(title)
            
            # iframeで表示（高さは適宜調整してください）
            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
