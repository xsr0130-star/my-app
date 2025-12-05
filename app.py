import streamlit as st
import streamlit.components.v1 as components
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import subprocess

# ==========================================
# 設定：入り口URL（ここを踏んでから行く）
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
            time.sleep(2) 

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
# 抽出ロジック（外科手術方式）
# ==========================================
def extract_only_content_keep_css(html_content, target_url):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. CSS（デザイン）だけは先に確保する
    styles = []
    # 外部CSSファイル
    for link in soup.find_all('link', rel='stylesheet'):
        styles.append(str(link))
    # ページ内のCSS
    for style in soup.find_all('style'):
        styles.append(str(style))
    
    style_html = "\n".join(styles)

    # 2. 本文が入っている「メインの箱」だけを探し出す
    # （画面全体 soup を使うとポップアップも残るので、中身だけ取り出す）
    
    max_score = 0
    best_html = "<div>本文が見つかりませんでした</div>"
    
    # 候補となるタグ（div, section, article, main）
    candidates = soup.find_all(['div', 'article', 'section', 'main', 'td'])

    for candidate in candidates:
        # スコア計算（文字数が多い場所＝本文の可能性が高い）
        text = candidate.get_text(strip=True)
        score = len(text)
        
        # リンクだらけの場所（メニュー）は除外
        links = candidate.find_all('a')
        link_len = sum([len(a.get_text()) for a in links])
        
        if score > 200: # ある程度長いブロックのみ対象
            if (link_len / score) < 0.5: # リンク文字率が半分以下
                if score > max_score:
                    max_score = score
                    # ここで .decompose() を使って、この候補の中にある邪魔なタグだけ消す
                    # script（プログラム）は絶対に消す！これがポップアップの正体
                    for bad in candidate.find_all(["script", "noscript", "iframe", "form", "button", "input"]):
                        bad.decompose()
                    
                    # 候補をHTMLとして保存
                    best_html = str(candidate)

    # 3. 新しいきれいなHTMLを組み立てる
    # 確保しておいたCSS ＋ 切り抜いた本文 ＝ 完成
    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <base href="{target_url}"> <!-- CSSのリンク切れ防止 -->
        {style_html}
        <style>
            body {{
                background-color: #fff;
                padding: 10px;
                font-family: sans-serif;
                overflow: auto !important; /* スクロール許可 */
            }}
            img {{ display: none !important; }} /* 画像は非表示 */
            /* 念のため固定配置を無効化するCSSも入れておく */
            div {{ position: static !important; }}
        </style>
    </head>
    <body>
        {best_html}
    </body>
    </html>
    """

    # タイトル取得
    title_text = "タイトルなし"
    if soup.title:
        title_text = soup.title.get_text(strip=True)

    return title_text, final_html

# ==========================================
# 画面構成
# ==========================================
st.set_page_config(page_title="H-Review Final", layout="centered")
st.title("💎 コンテンツ抽出リーダー")
st.caption("ポップアップの外側を切り捨て、中身だけを色付きで表示します。")

url = st.text_input("読みたい記事のURL", placeholder="https://...")

if st.button("抽出する"):
    if not url:
        st.warning("URLを入力してください。")
    else:
        status = st.empty()
        status.text("読み込み中...")
        
        html = fetch_html_via_route(url)

        if html:
            status.text("本文を切り抜き中...")
            title, final_html = extract_only_content_keep_css(html, url)
            status.empty()
            
            st.success("完了")
            st.subheader(title)
            
            # iframeで表示
            components.html(final_html, height=800, scrolling=True)
            
        else:
            status.error("読み込みに失敗しました。")
