"""Streamlit UI: Gemini同士の自律対話を観戦するブラウザ画面。

Run:
    streamlit run app.py
"""
from __future__ import annotations

import html
import os
import random
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


RANDOM_TOPICS = [
    "来年バズりそうな新サービスを1つ考えて、両者で具体案として合意してください。",
    "リモートワークと出社、これからの最適なバランスは何か。",
    "AIに任せていい仕事と、人間がやり続けるべき仕事の境界線は。",
    "副業で月10万円稼ぐ最も現実的な方法は。",
    "中小企業の採用力を3倍にするための1つの施策を決めてください。",
    "10年後も生き残る職業を3つに絞ってください。",
    "Z世代が本当に求めている福利厚生は何か、1つに絞って提案してください。",
    "通勤時間をビジネスチャンスに変える新サービスを1つ考えてください。",
    "ペット業界で今後伸びるサービスを1つ提案してください。",
    "シニア向けに本当に売れる新商品とは何かを決めてください。",
    "コンビニで売れる新カテゴリの商品を1つ提案してください。",
    "外食産業の人手不足を解決する画期的なアイデアを1つ決めてください。",
    "オンライン会議をもっと楽しくする工夫を1つ提案してください。",
    "若手社員のモチベーションを上げる最強の仕掛けを1つ決めてください。",
    "電気代を半分にする新しい家電のアイデアを1つ考えてください。",
    "もしオフィスを廃止するなら、代わりに何を作るべきか。",
    "30秒で人を笑わせる動画コンテンツの企画を1つ。",
    "新しい朝活ビジネスのアイデアを1つ提案してください。",
    "サブスクリプションが向くサービスと向かないサービスの境界線は。",
    "地方都市の人口減少を逆手に取った新ビジネスを1つ。",
]


def _bootstrap_secrets() -> None:
    """Streamlit Cloud の secrets を環境変数にコピー（dialogue_core から見えるように）。"""
    try:
        for key in (
            "GEMINI_API_KEY",
            "APP_PASSWORD",
            "MULTI_USER_MODE",
        ):
            if key in st.secrets and not os.environ.get(key):
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass  # secrets.toml が無い（ローカル .env 運用）でもエラーにしない


_bootstrap_secrets()


def _is_multi_user_mode() -> bool:
    """クラウド共有モード（ログ非保存・履歴非表示）。"""
    return os.environ.get("MULTI_USER_MODE", "").lower() in ("true", "1", "yes")


from dialogue_core import (  # noqa: E402
    DEFAULT_TOPIC,
    build_log_markdown,
    check_api_availability,
    dialogue_events,
    save_log,
)
from personas import CUSTOM_KEY, DEFAULT_A_KEY, DEFAULT_B_KEY, PERSONAS, RANDOM_KEY  # noqa: E402


st.set_page_config(page_title="AI議論", page_icon="🎙", layout="wide")


def _generate_aurora_palette() -> dict[str, str]:
    """パステル系オーロラ4色パレットを生成（明るく華やか）。

    色相環からおおむね 90 度ずつ離れた 4 色をランダムに選ぶ。
    彩度はやや控えめ、明度はかなり高めで「パステル × 明るい」配色。
    """
    hue_start = random.randint(0, 360)
    palette: dict[str, str] = {}
    for i in range(4):
        hue = (hue_start + i * 90 + random.randint(-15, 15)) % 360
        sat = random.randint(65, 85)
        light = random.randint(76, 88)
        alpha = round(random.uniform(0.92, 1.0), 2)
        palette[f"C{i + 1}"] = f"hsla({hue},{sat}%,{light}%,{alpha})"
    return palette


# セッション中は色を固定。新しいセッションで色変わる。
if "aurora_palette" not in st.session_state:
    st.session_state["aurora_palette"] = _generate_aurora_palette()
_AURORA = st.session_state["aurora_palette"]


# === Three.js 背景：パーティクル・ネットワーク（AI / ニューラルネット風） ===
# ダークブルー基調に、シアン・バイオレット・ブルーの粒子が漂い、近接するもの同士を
# 細い線で接続するクラシックな AI アニメーション。iframe で隔離して動かす。
THREE_BG_HTML = """<!DOCTYPE html>
<html><head>
<style>
  html, body { margin:0; padding:0; height:100%; background:transparent; overflow:hidden; }
  canvas { display:block; }
</style>
</head><body>
<canvas id="bg"></canvas>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script>
(function(){
  const canvas = document.getElementById('bg');
  const renderer = new THREE.WebGLRenderer({ canvas, alpha:true, antialias:true, powerPreference:'high-performance' });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  // fog で粒子が距離と共に静かに溶ける（やや控えめにして粒子を見せる）
  scene.fog = new THREE.FogExp2(0x010102, 0.05);
  const camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 100);
  camera.position.z = 12;

  // 円形ソフト発光スプライト
  function makeSprite(){
    const size = 128;
    const c = document.createElement('canvas');
    c.width = size; c.height = size;
    const ctx = c.getContext('2d');
    const g = ctx.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
    g.addColorStop(0.00, 'rgba(255,255,255,1.00)');
    g.addColorStop(0.20, 'rgba(255,255,255,0.75)');
    g.addColorStop(0.50, 'rgba(255,255,255,0.18)');
    g.addColorStop(1.00, 'rgba(255,255,255,0.00)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    return tex;
  }
  const sprite = makeSprite();

  // 控えめだが「ちゃんと見える」密度
  const isMobile = window.innerWidth < 768;
  const N = isMobile ? 56 : 120;

  const positions = new Float32Array(N*3);
  const colors = new Float32Array(N*3);
  const sizes = new Float32Array(N);
  const velocities = [];

  // 単色系 lavender / indigo パレット（彩度を落として静かに）
  const palette = [
    new THREE.Color(0x5e6ad2),  // Linear primary lavender
    new THREE.Color(0x818cf8),  // indigo-400
    new THREE.Color(0x6e7ad8),  // muted lavender
    new THREE.Color(0x4f56b0),  // deeper indigo
  ];

  for (let i=0; i<N; i++){
    positions[i*3]   = (Math.random()-0.5)*22;
    positions[i*3+1] = (Math.random()-0.5)*22;
    positions[i*3+2] = (Math.random()-0.5)*16;
    velocities.push({
      x:(Math.random()-0.5)*0.0045,
      y:(Math.random()-0.5)*0.0045,
      z:(Math.random()-0.5)*0.0045
    });
    const c = palette[Math.floor(Math.random()*palette.length)];
    // 明度はほぼフル（×0.92）で「ちゃんと見える」を担保しつつ単色寄せ
    colors[i*3]   = c.r * 0.92;
    colors[i*3+1] = c.g * 0.92;
    colors[i*3+2] = c.b * 0.92;
    // 8% を中サイズハブ、残りは細かい粒
    sizes[i] = Math.random() < 0.08 ? (2.0 + Math.random()*0.8) : (0.5 + Math.random()*0.45);
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geom.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const mat = new THREE.ShaderMaterial({
    uniforms: { pointTexture: { value: sprite } },
    vertexShader: `
      attribute float size;
      attribute vec3 color;
      varying vec3 vColor;
      void main() {
        vColor = color;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * (260.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: `
      uniform sampler2D pointTexture;
      varying vec3 vColor;
      void main() {
        vec4 t = texture2D(pointTexture, gl_PointCoord);
        if (t.a < 0.02) discard;
        gl_FragColor = vec4(vColor, 1.0) * t;
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geom, mat);
  scene.add(points);

  // 接続線は廃止（一番ノイズになる要素を抜くことで「プロっぽさ」が出る）

  let mouseX = 0, mouseY = 0, tx = 0, ty = 0;
  window.addEventListener('pointermove', (e) => {
    mouseX = (e.clientX / window.innerWidth) * 2 - 1;
    mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
  });

  const bound = 11;
  let frame = 0;
  function tick(){
    requestAnimationFrame(tick);
    frame++;
    const pos = geom.attributes.position.array;
    for (let i=0; i<N; i++){
      pos[i*3]   += velocities[i].x;
      pos[i*3+1] += velocities[i].y;
      pos[i*3+2] += velocities[i].z;
      if (pos[i*3]   >  bound || pos[i*3]   < -bound) velocities[i].x *= -1;
      if (pos[i*3+1] >  bound || pos[i*3+1] < -bound) velocities[i].y *= -1;
      if (pos[i*3+2] >  bound || pos[i*3+2] < -bound) velocities[i].z *= -1;
    }
    geom.attributes.position.needsUpdate = true;
    // 静かだが視認できる回転
    points.rotation.y += 0.00035;
    points.rotation.x += 0.00018;
    // パララックスは控えめだが反応はする
    tx += (mouseX * 0.55 - tx) * 0.022;
    ty += (mouseY * 0.55 - ty) * 0.022;
    camera.position.x = tx;
    camera.position.y = ty;
    // Z ドリフトは奥行きを感じる程度に
    camera.position.z = 12 + Math.sin(frame * 0.002) * 0.45;
    camera.lookAt(scene.position);
    renderer.render(scene, camera);
  }
  tick();

  window.addEventListener('resize', ()=>{
    camera.aspect = window.innerWidth/window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
})();
</script>
</body></html>"""


def _inject_three_bg() -> None:
    """Three.js 製のパーティクル背景を非表示の iframe で描画。

    iframe は CSS で position:fixed フル画面・z-index:-1・pointer-events:none に配置され、
    UI 要素のクリックを邪魔せず純粋な背景として機能する。
    """
    components.html(THREE_BG_HTML, height=10, scrolling=False)


# === Main UI styling: Figma準拠の派手アーケード調 ===
_SIDEBAR_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Dela+Gothic+One&display=swap" rel="stylesheet">
<style>
    /* ===== Three.js 背景レイヤー：完全フル画面の固定 iframe =====
       Streamlit の wrapper div / iframe を viewport いっぱいに広げ、z-index:0 で
       UI コンテンツ（z-index:10 以上）の下に敷く。pointer-events:none で透過。 */
    html, body {
        background-color: #010102 !important;
    }
    /* Streamlit の全レベルの wrapper を透明化して body の色 + iframe が見えるように */
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"],
    .main {
        background: transparent !important;
    }
    /* iframe ラッパー（複数バージョンに対応するため広めにセレクタ） */
    [data-testid="stCustomComponentV1"],
    [data-testid="stIFrame"],
    div[data-testid^="stCustom"],
    .stCustomComponentV1 {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        max-width: none !important;
        max-height: none !important;
        z-index: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
    }
    /* iframe 自体も同じく */
    [data-testid="stCustomComponentV1"] iframe,
    [data-testid="stIFrame"] iframe,
    iframe[title*="streamlit"],
    iframe[srcdoc*="THREE"] {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        border: 0 !important;
        background: transparent !important;
        pointer-events: none !important;
        z-index: 0 !important;
    }
    /* UI コンテンツは iframe より上に。stMainBlockContainer に positive z-index を */
    [data-testid="stMainBlockContainer"],
    .main .block-container {
        position: relative !important;
        z-index: 10 !important;
    }

    /* サイドバー非表示 + メインを左右真ん中に */
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stMain"] {
        margin-left: 0 !important;
        width: 100% !important;
        align-items: center !important;
    }
    [data-testid="stAppViewContainer"] > section {
        margin-left: 0 !important;
    }

    /* メイン中央寄せ：タイトルは広く、フォームは狭く */
    [data-testid="stMainBlockContainer"],
    .main .block-container {
        max-width: 820px !important;
        padding-top: 3rem !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }

    /* お題テキストエリア：Apple body 準拠（17px / -0.374px LS / 1.47 LH）+ rounded.lg + Apple md padding */
    div[data-testid="stTextArea"] {
        max-width: 660px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    [data-testid="stTextArea"] textarea {
        font-size: 17px !important;
        line-height: 1.47 !important;
        letter-spacing: -0.374px !important;
        min-height: 160px !important;
        border-radius: 18px !important;
        padding: 17px 22px !important;
        border: 1px solid #23252a !important;
        transition: border-color 0.12s ease !important;
    }
    [data-testid="stTextArea"] textarea:focus-visible {
        outline: 2px solid #5e69d1 !important;
        outline-offset: 2px !important;
        border-color: #34343a !important;
    }
    .stApp textarea::placeholder,
    div[data-testid="stTextArea"] textarea::placeholder {
        color: #62666d !important;
        opacity: 1 !important;
        -webkit-text-fill-color: #62666d !important;
    }

    /* セレクトボックスのラベル：Linear eyebrow タイポ（13px / 500 / +0.4px LS / uppercase） */
    div[data-testid="stSelectbox"] label,
    div[data-testid="stSelectbox"] label p {
        font-size: 13px !important;
        color: #8a8f98 !important;
        font-weight: 500 !important;
        letter-spacing: 0.4px !important;
        text-transform: uppercase !important;
    }
    /* セレクトボックス本体：Apple search-input 44px 高、flex 縦中央寄せで絵文字混じりでも切れない */
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 44px !important;
        border-radius: 11px !important;
        border: 1px solid #23252a !important;
        padding: 10px 14px !important;
        font-size: 15px !important;
        letter-spacing: -0.05px !important;
        line-height: 1.2 !important;
        display: flex !important;
        align-items: center !important;
        transition: border-color 0.12s ease !important;
    }
    div[data-testid="stSelectbox"] [data-baseweb="select"]:focus-within > div {
        border-color: #34343a !important;
    }

    /* === ボタン共通：Apple body サイズに準拠（17px / -0.374px LS / 11×22 padding / pill） === */
    div[data-testid="stButton"] button {
        border-radius: 9999px !important;
        padding: 11px 22px !important;
        font-family: 'Inter', 'Helvetica Neue', sans-serif !important;
        font-size: 17px !important;
        font-weight: 600 !important;
        letter-spacing: -0.374px !important;
        white-space: nowrap !important;
        line-height: 1.47 !important;
        min-height: auto !important;
        justify-content: center !important;
        text-align: center !important;
        transition: transform 0.12s ease !important;
    }
    div[data-testid="stButton"] button p {
        font-family: 'Inter', 'Helvetica Neue', sans-serif !important;
        font-size: 17px !important;
        font-weight: 600 !important;
        letter-spacing: -0.374px !important;
        white-space: nowrap !important;
        text-align: center !important;
    }
    /* Apple 共通: active で scale(0.95)、focus で 2px outline */
    div[data-testid="stButton"] button:active {
        transform: scale(0.95) !important;
    }
    div[data-testid="stButton"] button:focus-visible {
        outline: 2px solid #5e69d1 !important;
        outline-offset: 3px !important;
    }

    /* プライマリボタン（議論スタート）：オーロラ */
    @keyframes auroraDrift {
        0%   { background-position:   0%   0%; }
        25%  { background-position: 100%   0%; }
        50%  { background-position: 100% 100%; }
        75%  { background-position:   0% 100%; }
        100% { background-position:   0%   0%; }
    }
    @keyframes auroraGlow {
        0%, 100% {
            box-shadow:
                0 0 14px rgba(255, 255, 255, 0.22),
                inset 0 0 14px rgba(255, 255, 255, 0.08);
        }
        50% {
            box-shadow:
                0 0 30px rgba(255, 255, 255, 0.45),
                inset 0 0 22px rgba(255, 255, 255, 0.18);
        }
    }
    /* プライマリ：オーロラ復活 */
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #f8f5ff !important;
        background-image:
            radial-gradient(at 20% 20%, __AURORA_C1__ 0%, transparent 55%),
            radial-gradient(at 80% 25%, __AURORA_C2__ 0%, transparent 55%),
            radial-gradient(at 75% 80%, __AURORA_C3__ 0%, transparent 55%),
            radial-gradient(at 25% 80%, __AURORA_C4__ 0%, transparent 55%) !important;
        background-size: 200% 200% !important;
        animation:
            auroraDrift 6s ease-in-out infinite,
            auroraGlow 2.7s ease-in-out infinite !important;
        color: #000000 !important;
        border: 2px solid rgba(255, 255, 255, 0.6) !important;
        transition: transform 0.2s ease !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        animation:
            auroraDrift 3s ease-in-out infinite,
            auroraGlow 1.3s ease-in-out infinite !important;
    }
    div[data-testid="stButton"] button[kind="primary"] p {
        color: #000000 !important;
    }

    /* 戻るアクション（底部）：薄い枠付き控えめボタン
       body 先頭付け＋[kind="secondary"] 末尾付けで特異性を上げ、
       オーロラの kind="secondary" スタイルに勝つように */
    body [data-testid="element-container"]:has(.back-action-wrap)
        + [data-testid="element-container"] button[kind="secondary"] {
        background: transparent !important;
        background-image: none !important;
        background-color: transparent !important;
        animation: none !important;
        border: 1px solid #23252a !important;
        color: #d0d6e0 !important;
        padding: 8px 14px !important;
        min-height: auto !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        line-height: 1.20 !important;
        box-shadow: none !important;
        border-radius: 8px !important;
        letter-spacing: 0 !important;
        text-shadow: none !important;
    }
    body [data-testid="element-container"]:has(.back-action-wrap)
        + [data-testid="element-container"] button[kind="secondary"] p {
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
        color: #d0d6e0 !important;
        letter-spacing: 0 !important;
    }
    body [data-testid="element-container"]:has(.back-action-wrap)
        + [data-testid="element-container"] button[kind="secondary"]:hover {
        background: #141516 !important;
        background-image: none !important;
        border-color: #34343a !important;
        animation: none !important;
        transform: none !important;
    }

    /* トップ左の戻るリンク：純粋な <a> タグ。button 要素ではないので
       Streamlit のボタンスタイルと一切競合しない */
    a.back-top-link {
        color: #8a8f98 !important;
        font-size: 16px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 400 !important;
        text-decoration: none !important;
        display: inline-block;
        padding: 4px 8px;
    }
    a.back-top-link:hover {
        color: #d0d6e0 !important;
        text-decoration: none !important;
    }

    /* === セカンダリボタン：Linear button-secondary（surface-1 + hairline） === */
    div[data-testid="stButton"] button[kind="secondary"] {
        background: #0f1011 !important;
        background-image: none !important;
        color: #f7f8f8 !important;
        border: 1px solid #23252a !important;
        box-shadow: none !important;
        animation: none !important;
        transition: background-color 0.12s ease, border-color 0.12s ease !important;
    }
    div[data-testid="stButton"] button[kind="secondary"] p {
        color: #f7f8f8 !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background: #141516 !important;
        background-image: none !important;
        border-color: #34343a !important;
    }

    /* === チャット吹き出し：ガラス／フロスト効果（背景の Three.js 粒子を透過させる） === */
    [data-testid="stChatMessage"] {
        background: rgba(15, 16, 17, 0.42) !important;
        backdrop-filter: blur(14px) saturate(140%) !important;
        -webkit-backdrop-filter: blur(14px) saturate(140%) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        padding: 16px 20px !important;
        margin-bottom: 12px !important;
    }
    /* チャット内のテキストは少し明るめに、ガラス越しの可読性確保 */
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] span,
    [data-testid="stChatMessage"] div {
        color: #f1f3f5 !important;
    }
    /* キャプション（"ターン N · キャラ名"）はミュート */
    [data-testid="stChatMessage"] [data-testid="stCaptionContainer"] p {
        color: #8a8f98 !important;
    }

    /* === エクスパンダー：Linear rounded.lg (12px) + spacing.md (16px) + body LS (-0.05) === */
    [data-testid="stExpander"] {
        border: 1px solid #23252a !important;
        border-radius: 12px !important;
        background: transparent !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"] details {
        border: none !important;
        background: transparent !important;
    }
    [data-testid="stExpander"] details > summary {
        padding: 12px 16px !important;
        font-size: 14px !important;
        letter-spacing: -0.05px !important;
        border: none !important;
    }
    [data-testid="stExpander"] details > summary p {
        font-size: 14px !important;
        letter-spacing: -0.05px !important;
    }

    /* ボタン間スペーサ（PC基準値、スマホで縮める） */
    .btn-gap { height: 12px; }

    /* ランダムボタン直前のマーカー（::before で🎲を出す目印） */
    .random-btn-wrap { display: none; }

    /* ランダムボタンの先頭に🎲を文字より大きく表示（PC / スマホ共通） */
    body [data-testid="element-container"]:has(.random-btn-wrap)
        + [data-testid="element-container"] button[kind="secondary"]::before {
        content: "🎲";
        font-size: 1.45em;
        line-height: 1;
        margin-right: 10px;
        vertical-align: -2px;
        display: inline-block;
    }

    /* スマホ：VSの上下を更に詰める／ボタンを高め・幅80%・隙間半減 */
    @media (max-width: 768px) {
        /* スマホ時のみボタンラッパーを flex 中央寄せ（PCでは use_container_width が効くので触らない） */
        div[data-testid="stButton"] {
            display: flex !important;
            justify-content: center !important;
        }
        .ai-giron-vs {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin: 0 !important;
            font-size: 18px !important;
            line-height: 1 !important;
        }
        /* VS を含む列ブロックの上下余白を圧縮 */
        div[data-testid="stColumn"]:has(.ai-giron-vs) {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin-top: -10px !important;
            margin-bottom: -10px !important;
        }
        /* スタート／ランダムボタン：高さ 1.5倍、幅 80%、中央寄せ */
        div[data-testid="stButton"] button[kind="primary"],
        div[data-testid="stButton"] button[kind="secondary"] {
            padding-top: 18px !important;
            padding-bottom: 18px !important;
            width: 80% !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        /* 戻る系（back-action-wrap 直後）の secondary はタップ可能領域確保のため少し広めに */
        body [data-testid="element-container"]:has(.back-action-wrap)
            + [data-testid="element-container"] button[kind="secondary"] {
            padding: 12px 16px !important;
            width: auto !important;
        }
        /* ボタン間スペーサを半減 */
        .btn-gap { height: 6px !important; }
    }

    .ai-giron-title-main {
        font-family: 'Dela Gothic One', sans-serif !important;
        font-size: clamp(26px, 5.5vw, 38px) !important;
        color: white !important;
        text-align: center;
        margin: 14px auto 4px auto !important;
        line-height: 1.1;
        letter-spacing: -1.0px !important;
        white-space: nowrap !important;
        width: fit-content !important;
        display: block !important;
    }
    .ai-giron-title-login {
        font-family: 'Dela Gothic One', sans-serif !important;
        font-size: clamp(38px, 9vw, 72px) !important;
        color: white !important;
        text-align: center;
        margin: 18px 0 0px 0 !important;
        line-height: 1.05;
        letter-spacing: -1.8px !important;
        white-space: nowrap !important;
    }
    .ai-giron-vs {
        font-family: 'Dela Gothic One', sans-serif !important;
        font-size: 24px;
        color: white;
        text-align: center;
        padding-top: 28px;
        letter-spacing: -0.6px;
    }
</style>
"""
_aurora_css = _SIDEBAR_CSS
for _k, _v in _AURORA.items():
    _aurora_css = _aurora_css.replace(f"__AURORA_{_k}__", _v)
st.markdown(_aurora_css, unsafe_allow_html=True)

# Three.js パーティクル背景（ログイン画面・メイン画面のいずれでも表示される）
_inject_three_bg()


HELP_MARKDOWN = """
<div style="font-size: 0.86rem; color: #d0d6e0; line-height: 1.7;">

**🎯 何ができるか**

お題を放り込むと、2人のAIキャラが勝手に雑談しはじめます。最大2文の短いやりとりでテンポよく往復し、自然に「同じ方向に乗った」と判定された時点で雑談終了。終了後は議論の要約と、依頼者が次に動けるアクションを提案します。

**🎭 キャラ**

ふつうの人／アイデアマン／Z世代／ツッコミ／楽観派／悲観派／エンジニア／デザイナー／経営者／現場叩き上げ／新人（子供視点）／学者／営業／悪役、の14キャラを用意。
「ランダム」を選ぶとお題ごとに毎回違うキャラがランダム抽選されます。「カスタム」を選べば独自キャラもその場で作れます。

**⚙️ 動作の仕組み**

ブラウザ → Streamlit Cloud → Google Gemini API、という流れで動作します。
キャラA／キャラB／空気役（軽く話題を振る）／要約役、の4役を別人格の Gemini が分担。
同じモデルでも違うシステムプロンプトを与えることで別人格として振る舞います。
発言の長さや口調は全体トーン指示で「最大2文・60字目安・雑談寄り」に統制されています。

**⚠️ データ送信に関する注意**

お題・キャラ設定・会話の内容はすべて Google のサーバに送信され、保存される可能性があります。
無料プラン使用時、Google がモデル改善に使用する場合があります。

入力しないでください:
- 社外秘・社内秘情報
- 個人情報・顧客データ
- 未公開の経営情報、契約情報
- パスワード・APIキー等

ブレスト・雑談・公開情報ベースのお題でのみご利用ください。

**📊 仕様・制限**

- モデル: Gemini 3.1 Flash-Lite
- キャラ数: 14 + ランダム + カスタム
- 1日上限: 数百〜千リクエスト程度（全員合計、無料枠）
- 1議論あたり: 10〜20リクエスト消費
- 上限を超えるとその日は使用できません（翌朝復活）
- UI: Streamlit / ホスティング: Streamlit Community Cloud
- ソース: <a href="https://github.com/katochanpei/ai-dialogue" style="color: #5e6ad2;">github.com/katochanpei/ai-dialogue</a>

</div>
"""


def _render_help_panel(expanded: bool = False) -> None:
    """仕組みの解説パネル。注意点・仕様も含む。"""
    with st.expander("ℹ️ このツールについて（仕組み・注意点・仕様）", expanded=expanded):
        st.markdown(HELP_MARKDOWN, unsafe_allow_html=True)


def _check_password() -> bool:
    """パスワード認証。APP_PASSWORD 未設定なら認証スキップ（ローカル開発時）。"""
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected:
        return True
    if st.session_state.get("authenticated"):
        return True

    # ログイン画面ではサイドバーを非表示にしてスッキリ
    st.markdown(
        """
<style>
    section[data-testid="stSidebar"] { display: none !important; }

/* メインを縦横ど真ん中に */
[data-testid="stMain"] {
    min-height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}

[data-testid="stMainBlockContainer"],
.main .block-container {
    max-width: 420px !important;
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # 中央のカード型ログインフォーム
    st.markdown(
        """
<div style="display: flex; flex-direction: column; align-items: center; gap: 8px; padding-top: 8px;">
  <!-- 1行目: 🗣️ 🗣️ -->
  <div style="display: flex; gap: clamp(8px, 3vw, 24px); align-items: center;">
    <span style="font-size: clamp(64px, 18vw, 128px); line-height: 0.75;">🗣️</span>
    <span style="display: inline-block; transform: scaleX(-1);
                 font-size: clamp(64px, 18vw, 128px); line-height: 0.75;">🗣️</span>
  </div>
  <!-- 2行目: AIたち、どう思う？ -->
  <div class="ai-giron-title-login">AIたち、どう思う？</div>
  <!-- サブタイトル -->
  <p style="color: #8a8f98; font-size: 0.88rem; margin: 10px 0 80px 0; text-align: center;">
    AIの雑談、のぞいてみる？
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("login_form", clear_on_submit=False, border=False):
        pw = st.text_input(
            "パスワード",
            type="password",
            placeholder="パスワードを入力",
            label_visibility="collapsed",
            key="_pw_input",
        )
        submitted = st.form_submit_button(
            "ログイン",
            type="primary",
            use_container_width=True,
        )
        if submitted:
            if pw == expected:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("パスワードが違います")
    return False


def _init_state() -> None:
    defaults = {
        "running": False,
        "last_log_path": None,
        "last_log_md": None,
        "last_log_name": None,
        "viewing_log": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _persona_selector(side: str, default_key: str) -> dict:
    keys = list(PERSONAS.keys())
    idx = keys.index(default_key) if default_key in keys else 0
    selected_key = st.selectbox(
        "議論する人格を選択",
        keys,
        index=idx,
        format_func=lambda k: PERSONAS[k]["label"],
        key=f"persona_{side}_select",
    )

    if selected_key == CUSTOM_KEY:
        name = st.text_input("名前", value="カスタム", key=f"persona_{side}_custom_name")
        emoji = st.text_input("絵文字", value="✏️", key=f"persona_{side}_custom_emoji")
        system = st.text_area(
            "プロンプト",
            value="あなたは独自に設定されたキャラクターです。\n【性格】\n【口調】\n【話し方ルール】\n- 一度の発言は200字以内\n- 合意したら明確に同意を表明",
            height=160,
            key=f"persona_{side}_custom_system",
        )
        return {
            "key": "custom",
            "name": name or "カスタム",
            "emoji": emoji or "✏️",
            "label": f"{emoji or '✏️'} {name or 'カスタム'}",
            "system": system,
        }

    return PERSONAS[selected_key]


def _render_event(ev: dict, container) -> None:
    t = ev.get("type")
    if t == "turn":
        role = "user" if ev["persona"] == "A" else "assistant"
        with container.chat_message(role, avatar=ev["emoji"]):
            st.caption(f"ターン{ev['round']} ・ {ev['name']}")
            st.write(ev["text"])
    elif t == "facilitator":
        with container.chat_message("ai", avatar="🎤"):
            st.caption(f"ファシリテーター介入（{ev['round']}往復経過）")
            st.info(ev["text"])
    elif t == "retry":
        wait_sec = ev.get("wait_sec", 0)
        attempt = ev.get("attempt", 1)
        role = ev.get("role", "")
        container.warning(
            f"⏳ APIレート制限を検出（{role}）。"
            f"{wait_sec:.0f} 秒待機してから自動リトライします（{attempt}回目）..."
        )
    elif t == "agreement":
        container.success(f"✅ 合意成立！（{ev['round']}往復）")
    elif t == "end":
        container.warning(f"⏱ 最大往復数 {ev['round']} に到達。合意せず終了。")
    elif t == "summary":
        with container.container():
            st.markdown("---")
            st.markdown("# 📋 結論ブリーフィング")
            st.caption("議論の要約と、あなたの次のアクション")
            with st.container(border=True):
                if ev.get("topic"):
                    st.markdown(
                        f"""
<div style="
    background: linear-gradient(135deg,
        rgba(59, 130, 246, 0.16) 0%,
        rgba(30, 64, 175, 0.22) 100%);
    padding: 22px 26px;
    border-left: 5px solid #3b82f6;
    border-radius: 10px;
    margin-bottom: 26px;
">
  <div style="font-size: 0.78rem; color: #93c5fd; font-weight: 700;
              letter-spacing: 0.18em; margin-bottom: 10px;
              text-transform: uppercase;">
    📋 お題
  </div>
  <div style="font-size: 1.65rem; font-weight: 700; line-height: 1.55;
              color: #ffffff; letter-spacing: 0.01em;">
    {html.escape(ev["topic"])}
  </div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                st.markdown(ev["text"])
    elif t == "error":
        container.error(f"❌ {ev['text']}")


def _list_past_logs() -> list[Path]:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return sorted(log_dir.glob("*_dialogue.md"), reverse=True)


def _main_form() -> dict:
    """中央寄せの ChatGPT 風メインフォーム。お題が主役。"""
    # === セクション1: タイトル + サブタイトル ===
    st.markdown(
        """
<div style="display: flex; flex-direction: column; align-items: center;
            gap: 8px; padding-top: 24px; margin-bottom: 18px;">
  <!-- 1行目: 🗣️ 🗣️←反転 -->
  <div style="display: flex; gap: clamp(8px, 3vw, 24px); align-items: center;">
    <span style="font-size: clamp(48px, 12vw, 72px); line-height: 0.75;">🗣️</span>
    <span style="display: inline-block; transform: scaleX(-1);
                 font-size: clamp(48px, 12vw, 72px); line-height: 0.75;">🗣️</span>
  </div>
  <!-- 2行目: AIたち、どう思う？ -->
  <div class="ai-giron-title-main">AIたち、どう思う？</div>
  <!-- サブタイトル -->
  <p style="color: #8a8f98; font-size: 0.82rem; margin: 6px 0 0 0; text-align: center;">
    AIの雑談、のぞいてみる？
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    # === セクション間スペース（タイトル → フォーム） ===
    st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)

    # === セクション2: 入力フォーム本体 ===
    # お題テキストエリア（プレースホルダで入力を促す）
    topic_input = st.text_area(
        "お題",
        value="",
        placeholder="気になること、ちょっと入れてみて\n（空欄でもOK。ランダムでお題出ます）",
        height=160,
        key="topic_input",
        label_visibility="collapsed",
        help="空のまま「議論スタート！」を押すと、20 種類のお題プールからランダムに選ばれます。",
    )
    topic = topic_input.strip() or random.choice(RANDOM_TOPICS)

    # ─── お題 → キャラ間の余白 ───
    st.markdown('<div style="height: 0px;"></div>', unsafe_allow_html=True)

    # キャラA / VS / キャラB
    col_a, col_vs, col_b = st.columns([298, 80, 298])
    with col_a:
        persona_a = _persona_selector("A", DEFAULT_A_KEY)
    with col_vs:
        st.markdown('<div class="ai-giron-vs">VS</div>', unsafe_allow_html=True)
    with col_b:
        persona_b = _persona_selector("B", DEFAULT_B_KEY)

    # ─── キャラ → ボタン間の余白 ───
    st.markdown('<div style="height: 32px;"></div>', unsafe_allow_html=True)

        # ボタン群（縦並び・中央寄せ）
    _, btn_center, _ = st.columns([1, 4, 1])
    with btn_center:
        start = st.button(
            "ちょっと聞いてみる👂",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.running,
        )

    # === セクション間スペース（フォーム → 折りたたみ） ===
    st.markdown('<div style="height: 48px;"></div>', unsafe_allow_html=True)

    # === セクション3: 折りたたみ要素（詳細パラメータ／ヘルプ） ===
    st.markdown(
        """
<style>
  [data-testid="stExpander"] { margin-bottom: 0px !important; }
</style>
""",
        unsafe_allow_html=True,
    )
    with st.expander("⚙️ 詳細パラメータ", expanded=False):
        max_rounds = st.slider("最大往復", 1, 30, 20)
        interval = st.slider("ファシリテーター介入間隔", 1, 10, 3)
        delay = st.slider("発言間スリープ (秒)", 0.0, 5.0, 2.0, 0.5)

    if not _is_multi_user_mode():
        with st.expander("📜 過去ログ", expanded=False):
            log_files = _list_past_logs()
            if log_files:
                log_labels = ["（選択してください）"] + [p.stem for p in log_files]
                picked = st.selectbox(
                    "過去ログ", log_labels, label_visibility="collapsed"
                )
                if picked != "（選択してください）":
                    st.session_state.viewing_log = next(
                        p for p in log_files if p.stem == picked
                    )
                else:
                    st.session_state.viewing_log = None
            else:
                st.caption("まだログがありません")

    _render_help_panel(expanded=False)

    return {
        "topic": topic,
        "persona_a": persona_a,
        "persona_b": persona_b,
        "max_rounds": max_rounds,
        "interval": interval,
        "delay": delay,
        "start": start,
    }


def _render_past_log(log_path: Path) -> None:
    st.subheader(f"📜 {log_path.stem}")
    st.markdown(log_path.read_text(encoding="utf-8"))
    if st.button("← 閉じる"):
        st.session_state.viewing_log = None
        st.rerun()


def _randomize_cfg(cfg: dict) -> dict:
    """お題・キャラ・パラメータを全てランダムに上書きする。"""
    keys_pool = [k for k in PERSONAS.keys() if k not in (CUSTOM_KEY, RANDOM_KEY)]
    a_key, b_key = random.sample(keys_pool, 2)
    return {
        **cfg,
        "topic": random.choice(RANDOM_TOPICS),
        "persona_a": PERSONAS[a_key],
        "persona_b": PERSONAS[b_key],
        "max_rounds": random.randint(5, 10),
        "interval": random.randint(2, 4),
        "delay": round(random.uniform(1.0, 2.5), 1),
    }


def _resolve_random_personas(cfg: dict) -> dict:
    """persona_a / persona_b の key が "random" のとき、実ペルソナへ解決する。

    両方ランダムなら 2 つ異なるキャラ、片方のみなら相手と被らないキャラを抽選する。
    """
    keys_pool = [k for k in PERSONAS.keys() if k not in (CUSTOM_KEY, RANDOM_KEY)]
    a_is_random = cfg["persona_a"].get("key") == RANDOM_KEY
    b_is_random = cfg["persona_b"].get("key") == RANDOM_KEY
    if not a_is_random and not b_is_random:
        return cfg
    new_cfg = dict(cfg)
    if a_is_random and b_is_random:
        a_key, b_key = random.sample(keys_pool, 2)
        new_cfg["persona_a"] = PERSONAS[a_key]
        new_cfg["persona_b"] = PERSONAS[b_key]
    elif a_is_random:
        used = cfg["persona_b"].get("key")
        choices = [k for k in keys_pool if k != used] or keys_pool
        new_cfg["persona_a"] = PERSONAS[random.choice(choices)]
    else:
        used = cfg["persona_a"].get("key")
        choices = [k for k in keys_pool if k != used] or keys_pool
        new_cfg["persona_b"] = PERSONAS[random.choice(choices)]
    return new_cfg


def _run_dialogue(cfg: dict) -> None:
    st.session_state.running = True

    # === お題（最も目立つ大きなパネル） ===
    st.markdown(
        f"""
<div style="
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
    padding: 26px 32px;
    border-radius: 14px;
    margin: 14px 0 22px 0;
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3);
">
  <div style="color: #bfdbfe; font-size: 0.78rem; font-weight: 700;
              letter-spacing: 0.18em; margin-bottom: 12px; text-transform: uppercase;">
    📋 お 題
  </div>
  <div style="color: #ffffff; font-size: 1.45rem; font-weight: 600;
              line-height: 1.55;">
    {html.escape(cfg["topic"])}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # === 議論ヘッダ（お題より控えめ） ===
    st.subheader(
        f"💬 議論: {cfg['persona_a']['label']}   vs   {cfg['persona_b']['label']}"
    )
    st.caption(
        f"⚙️ 最大 {cfg['max_rounds']} 往復 / "
        f"{cfg['interval']} 往復ごとにファシリテーター介入 / "
        f"発言間 {cfg['delay']} 秒"
    )

    chat_container = st.container()
    status_container = st.container()
    events_log: list[dict] = []
    pending_placeholder = None  # 「考え中」用の差し替えスロット
    retry_placeholder = None    # リトライ通知用の差し替えスロット

    def _show_thinking(ev: dict):
        """次の発言が来るまで「考え中...」を表示するプレースホルダを作る。"""
        nonlocal pending_placeholder
        pending_placeholder = chat_container.empty()
        with pending_placeholder.container():
            with st.chat_message("assistant", avatar=ev.get("emoji", "💭")):
                st.caption(f"・ {ev.get('role', '')}")
                st.markdown(f"_{ev.get('message', '考え中...')}_")

    def _swap_into_placeholder(render_fn):
        """thinking placeholder の中身を実際の発言で置き換える。"""
        nonlocal pending_placeholder
        if pending_placeholder is None:
            return False
        with pending_placeholder.container():
            render_fn()
        pending_placeholder = None
        return True

    def _clear_placeholder():
        nonlocal pending_placeholder
        if pending_placeholder is not None:
            pending_placeholder.empty()
            pending_placeholder = None

    def _show_retry(ev: dict):
        """リトライ通知を消去可能なスロットに描画。既存通知があれば差し替える。"""
        nonlocal retry_placeholder
        if retry_placeholder is None:
            retry_placeholder = status_container.empty()
        wait_sec = ev.get("wait_sec", 0)
        attempt = ev.get("attempt", 1)
        role = ev.get("role", "")
        with retry_placeholder.container():
            st.warning(
                f"⏳ APIレート制限を検出（{role}）。"
                f"{wait_sec:.0f} 秒待機してから自動リトライします（{attempt}回目）..."
            )

    def _clear_retry():
        nonlocal retry_placeholder
        if retry_placeholder is not None:
            retry_placeholder.empty()
            retry_placeholder = None

    try:
        for ev in dialogue_events(
            cfg["topic"],
            cfg["persona_a"],
            cfg["persona_b"],
            max_rounds=cfg["max_rounds"],
            intervention_interval=cfg["interval"],
            delay_sec=cfg["delay"],
        ):
            events_log.append(ev)
            t = ev.get("type")

            if t == "thinking":
                _show_thinking(ev)

            elif t == "turn":
                _clear_retry()
                def _render_turn(_ev=ev):
                    role = "user" if _ev["persona"] == "A" else "assistant"
                    with st.chat_message(role, avatar=_ev["emoji"]):
                        st.caption(f"ターン{_ev['round']} ・ {_ev['name']}")
                        st.write(_ev["text"])
                if not _swap_into_placeholder(_render_turn):
                    _render_event(ev, chat_container)

            elif t == "facilitator":
                _clear_retry()
                def _render_fac(_ev=ev):
                    with st.chat_message("ai", avatar="🎤"):
                        st.caption(f"ファシリテーター介入（{_ev['round']}往復経過）")
                        st.info(_ev["text"])
                if not _swap_into_placeholder(_render_fac):
                    _render_event(ev, chat_container)

            elif t == "summary":
                _clear_placeholder()
                _clear_retry()
                _render_event(ev, status_container)

            elif t in {"agreement", "end", "error"}:
                _clear_placeholder()
                _clear_retry()
                _render_event(ev, status_container)

            elif t == "retry":
                # 既存の retry スロットへ差し替える形で表示（古い通知は消える）
                _show_retry(ev)

            else:
                _render_event(ev, chat_container)
    finally:
        from datetime import datetime as _dt
        log_md = build_log_markdown(
            events_log,
            cfg["topic"],
            cfg["persona_a"]["name"],
            cfg["persona_b"]["name"],
        )
        if _is_multi_user_mode():
            # クラウド共有モード: ディスクには保存しない（誰も見られないため無駄）
            timestamp = _dt.now().strftime("%Y-%m-%d_%H%M%S")
            log_filename = f"{timestamp}_dialogue.md"
            st.session_state.last_log_path = None
        else:
            # ローカル: ディスクに保存して履歴に残す
            log_path = save_log(
                events_log,
                cfg["topic"],
                cfg["persona_a"]["name"],
                cfg["persona_b"]["name"],
            )
            log_filename = log_path.name
            st.session_state.last_log_path = log_path
        st.session_state.last_log_md = log_md
        st.session_state.last_log_name = log_filename
        st.session_state.running = False

    st.markdown("---")
    st.subheader("📥 議論ログのダウンロード")
    st.download_button(
        "議論ログをダウンロード",
        data=log_md.encode("utf-8"),
        file_name=log_filename,
        mime="text/markdown",
        type="primary",
    )
    st.caption(
        "💾 議論ログは画面を離れると参照できなくなります。"
        "手元に残したい場合は、上のボタンからダウンロードしてください。"
    )


def _reset_dialogue_state() -> None:
    """議論完了後の状態をクリアしてフォームに戻すための初期化。"""
    for key in ("last_log_md", "last_log_name", "last_log_path"):
        if key in st.session_state:
            st.session_state[key] = None


def main() -> None:
    if not _check_password():
        return
    _init_state()

    # クエリパラメータ経由の「やっぱり戻る」リンク検出
    if "back" in st.query_params:
        _reset_dialogue_state()
        st.query_params.clear()
        st.rerun()

    if st.session_state.viewing_log:
        _render_past_log(st.session_state.viewing_log)
        return

    # フォームを差し替え可能なスロットに入れる
    form_slot = st.empty()
    with form_slot.container():
        cfg = _main_form()

    if cfg["start"]:
        # フォームを消して画面を議論専用に切り替える
        form_slot.empty()

        # 左上の戻るリンク（純粋な <a> タグ、button要素ではない）
        st.markdown(
            '<a href="?back=1" class="back-top-link">← やっぱり戻る</a>',
            unsafe_allow_html=True,
        )

        cfg = _resolve_random_personas(cfg)

        with st.spinner("Gemini API の利用可否を確認しています..."):
            ok, message, code = check_api_availability()
        if not ok:
            st.error("❌ Gemini API が現在利用できません。議論を開始できません。")
            st.markdown(f"**理由:**\n\n{message}")
            with st.expander("エラーコード（詳細）"):
                st.code(code)
            return

        _run_dialogue(cfg)

        # 議論完了後：底部に控えめな戻るリンク
        st.markdown('<div style="height: 32px;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="back-action-wrap"></div>', unsafe_allow_html=True)
        if st.button("← 新しい議論を始める", key="back_to_form_btn"):
            _reset_dialogue_state()
            st.rerun()


if __name__ == "__main__":
    main()
