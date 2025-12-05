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
# ブラウザ操作（年齢確認ボタンをクリックする処理を追加）
# ==========================================
def fetch_html_bypass_age_gate(target_url):
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
            page.wait_for_load_state("domcontentloaded") # 読み込み待ち

            # === 【追加】年齢確認ボタンを探して押す ===
            # よくあるボタンの言葉をリストアップして、見つけたらクリックする
            age_keywords = ["はい", "Yes", "YES", "Enter", "18歳以上", "Entry", "入場", "承諾"]
            
            for word in age_keywords:
                try:
                    # 画面内にその言葉を含むボタンやリンクがあればクリック（タイムアウト短め）
                    # 見つからなければエラーになるので無視して次へ
                    page.get_by_text(word).first.click(timeout=500)
                    print(f"Clicked: {word}")
                    time.sleep(1) # クリック後の画面遷移待ち
                    break # 1つ押せたら終了
                except:
                    continue
            
            # 3. 最終的なHTMLを取得
            return page.content()

        except Exception as e:
            st.error(f"エラー: {e}")
            return None
        finally:
            browser.close()

# ==========================================
# 抽出ロジック（CSS維持 ＋ ポップアップ強制削除）
# ==========================================
def clean_html_remove_popups(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Base URL設定
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))
    
    base_tag = soup.new_tag("base", href=target_url)
    if soup.head.base:
        soup.head.base.replace_with(base_tag)
    else:
        soup.head.insert(0, base_tag)

    # 2. 不要タグ削除（imgは残すか消すか選べます。今回は消す設定）
    garbage_tags = ["script", "noscript", "iframe", "form", "button", "input", "nav", "footer", "header"]
    for tag_name in garbage_tags:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 3. 【強力】ポップアップを強制的に消すCSSを注入
    # どんなIDかわからないため、「画面全体を覆う系」のCSSプロパティを無効化し、
    # スクロール禁止(overflow: hidden)を解除する
    custom_style = soup.new_tag("style")
    custom_style.string = """
        body { 
            background-color: #fff !important; 
            font-family: sans-serif; 
            overflow: auto !important; /* スクロール禁止を強制解除 */
            height: auto !important;
        }
        img { display: none !important; }
        
        /* ポップアップによく使われるクラス名やIDを推測して非表示にする */
        #age-verification, #modal, .modal, .overlay, .popup, #popup, .dialog, #age_check, .age_check {
            display: none !important;
            opacity: 0 !important;
            z-index: -9999 !important;
            visibility: hidden !important;
        }
        
        /* 画面全体を覆う固定要素（オーバーレイ）をまとめて消す荒技 */
        div[style*="position: fixed"], div[style*="z-index: 999"], div[style*="z-index: 1000"] {
            /* 注意：これをやると大切なヘッダーも消える可能性がありますが、本文を読むには有効です */
            /* display: none !important; */ 
        }
    """
    soup.head.append(custom_style)

    title_text = "タイトルなし"
    if soup.title:
        title_text = soup.title.get_text(strip=True)

    return title_text, str(soup)

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Unlocker", layout="centered")
st.title("🔓 年齢認証突破リーダー")
st.caption("年齢確認ボタンを自動クリック＆ポップアップを強制排除します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("突破して表示"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("サイトにアクセス中...")
        
        # 年齢認証突破ロジックを使用
        html = fetch_html_bypass_age_gate(url)

        if html:
            status.text("ポップアップ除去中...")
            title, final_html = clean_html_remove_popups(html, url)
            status.empty()
            
            st.success("完了")
            st.subheader(title)
            
            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
