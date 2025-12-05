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
# ブラウザ操作（JSでポップアップを破壊する）
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
            time.sleep(2) # ポップアップが出るのを少し待つ

            # 3. 【最強の処理】JavaScriptを実行して、邪魔な要素を内側から破壊する
            # (画面全体を覆っている position:fixed の要素を全て削除します)
            page.evaluate("""
                () => {
                    // 1. よくある「年齢確認ボタン」があればクリックを試みる
                    const buttons = document.querySelectorAll('a, button, input[type="button"], div');
                    const keywords = ['はい', 'YES', 'Yes', '18歳', 'Enter', '入り口', '入場', 'adult'];
                    for (let btn of buttons) {
                        if (keywords.some(k => btn.innerText && btn.innerText.includes(k))) {
                            btn.click(); // 見つけたら即クリック
                            // break; // 複数あるかもしれないのでbreakしない
                        }
                    }

                    // 2. 画面を覆う「邪魔な膜（オーバーレイ）」を強制削除
                    // z-indexが高く、fixedまたはabsoluteで配置されている要素を狙い撃ち
                    const allDivs = document.querySelectorAll('body > div, body > section, body > span');
                    allDivs.forEach(div => {
                        const style = window.getComputedStyle(div);
                        // 画面全体を覆っているか、浮いている要素で、中身が少なければ削除対象
                        if ((style.position === 'fixed' || style.position === 'absolute') && style.zIndex > 100) {
                            div.remove(); // 削除！
                        }
                    });

                    // 3. スクロール禁止（overflow:hidden）を強制解除
                    document.body.style.overflow = 'visible';
                    document.body.style.height = 'auto';
                    document.body.style.position = 'static';
                    document.documentElement.style.overflow = 'visible';
                }
            """)
            
            time.sleep(1) # 削除処理の反映待ち

            # 処理後のきれいになったHTMLを返す
            return page.content()

        except Exception as e:
            st.error(f"エラー: {e}")
            return None
        finally:
            browser.close()

# ==========================================
# 抽出ロジック（CSS維持）
# ==========================================
def clean_html_keep_css(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Base URL（CSSリンク切れ防止）
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))
    
    base_tag = soup.new_tag("base", href=target_url)
    if soup.head.base:
        soup.head.base.replace_with(base_tag)
    else:
        soup.head.insert(0, base_tag)

    # 2. 不要タグ削除（ポップアップは既にブラウザ側で消しているので、ここではスクリプト等を消す）
    garbage_tags = ["script", "noscript", "iframe", "form", "input", "nav", "footer", "header"]
    for tag_name in garbage_tags:
        for tag in soup.find_all(tag_name):
            tag.decompose()
            
    # 画像を表示したくない場合はここで消す（今回は残す設定にしてみます。邪魔なら復活させてください）
    # for img in soup.find_all("img"):
    #     img.decompose()

    # 3. タイトル取得
    title_text = "タイトルなし"
    if soup.title:
        title_text = soup.title.get_text(strip=True)

    return title_text, str(soup)

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Ultra", layout="centered")
st.title("🔨 ポップアップ破壊リーダー")
st.caption("邪魔な表示を強制的に削除して中身を表示します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("破壊して読む"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("サイトに侵入中...")
        
        # JS破壊ロジックを実行
        html = fetch_html_force_clean(url)

        if html:
            status.text("整理中...")
            title, final_html = clean_html_keep_css(html, url)
            status.empty()
            
            st.success("完了")
            st.subheader(title)
            
            # iframeで表示
            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
