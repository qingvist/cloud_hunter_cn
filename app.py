import os
import sqlite3
import datetime
import hashlib
import base64
import time
import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import platform

# ==========================================
# 🤖 核心配置
# ==========================================
AVAILABLE_MODELS = [
    "gemini-2.5-flash-lite", 
    "gemini-2.5-flash",       
    "gemini-1.5-flash",       
    "gemini-2.0-flash-exp"    
]

# ==========================================
# 📖 1. 字典库
# ==========================================
CLOUD_TRANSLATIONS = {
    "积云": "Cumulus", "淡积云": "Cumulus humilis", "碎积云": "Cumulus fractus", "浓积云": "Cumulus congestus",
    "层云": "Stratus", "雾": "Fog", "飞机尾迹": "Contrail",
    "层积云": "Stratocumulus", "高积云": "Altocumulus", "高层云": "Altostratus",
    "卷云": "Cirrus", "卷层云": "Cirrostratus", "卷积云": "Cirrocumulus", "密卷云": "Cirrus spissatus", "钩卷云": "Cirrus uncinus",
    "雨层云": "Nimbostratus", "积雨云": "Cumulonimbus", "幡状云": "Virga",
    "波状高积云": "Altocumulus undulatus", "透光高积云": "Altocumulus translucidus", "絮状高积云": "Altocumulus floccus", "堡状高积云": "Altocumulus castellanus",
    "日晕": "Halo", "幻日": "Sun Dog", "彩虹": "Rainbow", "双彩虹": "Double Rainbow", "火彩虹": "Circumhorizontal Arc",
    "云隙光": "Crepuscular Rays", "反云隙光": "Anticrepuscular Rays", "虹彩云": "Iridescence",
    "乳状云": "Mammatus", "网状云": "Lacunosus", "糙面云": "Asperitas",
    "荚状云": "Lenticularis", "夜光云": "Noctilucent", "滚轴云": "Roll Cloud", "管状云": "Tube Cloud",
    "珠母云": "Nacreous", "马蹄云": "Horseshoe Vortex", "雨幡洞": "Fallstreak Hole",
    "开尔文-赫姆霍兹波": "Kelvin-Helmholtz", "海啸云": "Shelf Cloud",
    "红色精灵": "Red Sprite", "史蒂夫现象": "STEVE"
}

def get_bilingual_name(c_name):
    en_name = CLOUD_TRANSLATIONS.get(c_name, "")
    if en_name:
        return f"{c_name} <span style='opacity:0.6; font-size:0.8em; font-family:serif;'>{en_name}</span>"
    return c_name

ACHIEVEMENTS = {
    "👶 萌新入坑": {"clouds": ["积云", "层云", "飞机尾迹"], "icon": "🌱", "desc": "收集积云、层云或飞机尾迹中的任意 2 种"},
    "☔ 暴雨将至": {"clouds": ["积雨云", "雨层云", "碎积云"], "icon": "🌧️", "desc": "收集积雨云、雨层云等预示降水的云 (任意2种)"},
    "☁️ 云端漫步": {"clouds": ["卷云", "卷积云", "卷层云"], "icon": "🕊️", "desc": "集齐所有高云族 (卷云系列)"},
    "🌈 光之美学": {"clouds": ["彩虹", "双彩虹", "日晕", "虹彩云", "云隙光"], "icon": "🌈", "desc": "收集 3 种以上的大气光学现象"},
    "⛈️ 风暴领主": {"clouds": ["积雨云", "乳状云", "海啸云", "糙面云"], "icon": "⚡", "desc": "收集 2 种以上的风暴伴生云"},
    "👽 异星来客": {"clouds": ["荚状云", "马蹄云", "开尔文-赫姆霍兹波", "滚轴云"], "icon": "🛸", "desc": "收集 1 种形状极其怪异的云"}
}

OFFICIAL_SCORES = {
    "积云": 10, "淡积云": 10, "碎积云": 10, "层云": 10, "雾": 5, "飞机尾迹": 5,
    "层积云": 15, "高积云": 15, "高层云": 15, "卷云": 15, "卷层云": 15, "雨层云": 20, "卷积云": 25, "积雨云": 25, "浓积云": 20, "幡状云": 25, "絮状高积云": 25,
    "波状高积云": 30, "透光高积云": 30, "日晕": 30, "彩虹": 35, "云隙光": 30, "乳状云": 35, "网状云": 35, "堡状高积云": 35, "幻日": 35, "反云隙光": 35,
    "双彩虹": 40, "荚状云": 40, "虹彩云": 40, "糙面云": 45, "夜光云": 45, "滚轴云": 45, "管状云": 45,
    "珠母云": 50, "马蹄云": 50, "雨幡洞": 50, "开尔文-赫姆霍兹波": 55, "海啸云": 55, "火彩虹": 60, "红色精灵": 80, "史蒂夫现象": 80
}

MAX_POSSIBLE_SCORE = sum(OFFICIAL_SCORES.values())

def get_official_score(cloud_name, ai_suggested_score):
    if cloud_name in OFFICIAL_SCORES: return OFFICIAL_SCORES[cloud_name]
    sorted_keys = sorted(OFFICIAL_SCORES.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in cloud_name or cloud_name in key: return OFFICIAL_SCORES[key]
    return ai_suggested_score

def calculate_tier_from_score(score):
    if score <= 10: return "N"
    if score <= 29: return "R"
    if score <= 39: return "SR"
    if score <= 49: return "SSR"
    return "UR"

# ==========================================
# 🎨 2. UI 样式配置
# ==========================================
st.set_page_config(page_title="Cloud Hunter Pro", page_icon="☁️", layout="wide")

def inject_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&display=swap');
        
        .stApp {
            background-color: #fdfbf7;
            background-image: radial-gradient(#e0e0e0 1px, transparent 1px);
            background-size: 20px 20px;
            font-family: "Lora", "KaiTi", "STKaiti", "SimSun", serif;
            color: #2c3e50;
        }
        
        /* 隐藏 Streamlit 默认的顶部红线装饰 */
        header[data-testid="stHeader"] {
            background: transparent;
        }
        
        .apple-card {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            border: 1px solid rgba(0,0,0,0.05);
            margin-bottom: 20px;
            min-height: 520px; 
            display: flex;
            flex-direction: column;
        }
        
        .mini-dashboard {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 15px 25px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
            border: 1px solid rgba(0,0,0,0.05);
            height: 98px; 
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .preview-container {
            width: 100%;
            height: 350px;
            background-color: #fff;
            border: 1px solid #eee;
            padding: 10px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        .preview-container img {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        
        /* === 通用按钮样式 === */
        .stButton>button {
            border-radius: 8px;
            height: 3.5em;
            font-family: "KaiTi", "STKaiti", serif;
            font-weight: 600;
            border: none;
            background: #2c3e50;
            color: #fff;
            transition: all 0.3s ease;
            width: 100%;
        }
        .stButton>button:hover {
            background: #34495e;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(44, 62, 80, 0.3);
        }
        
        /* === 侧边栏工具按钮专用样式 (强制变灰、变小) === */
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button {
            background-color: #f0f2f5 !important;
            color: #7f8c8d !important;
            border: 1px solid #dcdde1 !important;
            height: 2.8em !important;
            font-size: 0.85em !important;
            box-shadow: none !important;
            border-radius: 6px !important;
        }
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button:hover {
            background-color: #e2e6ea !important;
            color: #2c3e50 !important;
            border-color: #bdc3c7 !important;
        }

        [data-testid="stSidebar"] {
            background-color: #faf9f6;
            border-right: 1px solid #e0e0e0;
        }
        
        h1, h2, h3, h4 {
            font-family: "Lora", "KaiTi", "STKaiti", serif;
            color: #2c3e50;
            font-weight: bold;
        }
        
        .tooltip-target {
            cursor: help;
            border-bottom: 1px dashed #bdc3c7;
        }

        /* === ☁️ 像素云动画 (使用 SVG Data URI 修复破图问题) === */
        @keyframes float {
            0% { transform: translateY(0px); }
            50% { transform: translateY(-8px); }
            100% { transform: translateY(0px); }
        }
        
        .pixel-cloud-container {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            margin-bottom: 5px;
        }
        
        .pixel-cloud {
            width: 45px;
            opacity: 0.6;
            animation: float 4s ease-in-out infinite;
        }
        
        .pixel-cloud.right {
            animation-delay: 2s; /* 错开动画时间 */
        }
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# ==========================================
# 🔧 3. 后端逻辑
# ==========================================

# os.environ["HTTP_PROXY"] = "http://127.0.0.1:10809"
#os.environ["HTTPS_PROXY"] = "http://127.0.0.1:10809"

def init_db():
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cloud_name TEXT,
            tier TEXT,
            score INTEGER,
            science_fact TEXT,
            weather_tip TEXT,
            image_data BLOB,
            image_hash TEXT UNIQUE, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def delete_record(record_id):
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    c.execute('DELETE FROM history WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def fix_legacy_scores_forced():
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    c.execute('SELECT id, cloud_name, score, tier FROM history')
    rows = c.fetchall()
    updated_count = 0
    for row in rows:
        r_id, r_name, r_score, r_tier = row
        if r_score == 0: continue
        correct_score = get_official_score(r_name, r_score)
        correct_tier = calculate_tier_from_score(correct_score)
        if r_score != correct_score or r_tier != correct_tier:
            c.execute('UPDATE history SET score = ?, tier = ? WHERE id = ?', (correct_score, correct_tier, r_id))
            updated_count += 1
    if updated_count > 0: conn.commit()
    conn.close()
    return updated_count

init_db()

def get_record_by_hash(img_hash):
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    c.execute('SELECT cloud_name, tier, score, science_fact, weather_tip, timestamp FROM history WHERE image_hash = ?', (img_hash,))
    result = c.fetchone()
    conn.close()
    return result

def check_cloud_discovered(cloud_name):
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    c.execute('SELECT count(*) FROM history WHERE cloud_name = ?', (cloud_name,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def normalize_tier(raw_tier):
    if not raw_tier: return "N"
    t = str(raw_tier).upper().strip()
    clean = t.split()[0]
    if clean in ["UR", "SSR", "SR", "R", "N"]: return clean
    return "N"

def save_to_db(cloud_name, tier, score, science_fact, weather_tip, image_bytes, image_hash):
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    try:
        clean_tier = normalize_tier(tier)
        c.execute('INSERT INTO history (cloud_name, tier, score, science_fact, weather_tip, image_data, image_hash) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (cloud_name, clean_tier, score, science_fact, weather_tip, image_bytes, image_hash))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_history():
    conn = sqlite3.connect('clouds.db')
    c = conn.cursor()
    c.execute('SELECT id, cloud_name, tier, score, science_fact, weather_tip, image_data, image_hash, timestamp FROM history ORDER BY id DESC')
    data = c.fetchall()
    conn.close()
    return data

def image_to_base64(image_bytes):
    encoded = base64.b64encode(image_bytes).decode()
    return f"data:image/jpeg;base64,{encoded}"

def make_square_thumbnail(image_bytes, size=(300, 300)):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
        return img
    except:
        return None

# ==========================================
# 🎨 4. 视觉工具
# ==========================================

TIER_COLORS = {"UR": "#c0392b", "SSR": "#f1c40f", "SR": "#8e44ad", "R": "#2980b9", "N": "#7f8c8d"}

def get_tier_color(tier):
    clean = normalize_tier(tier)
    return TIER_COLORS.get(clean, "#7f8c8d")

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def load_chinese_font(size):
    system = platform.system()
    font_paths = []
    if system == "Windows":
        font_paths = ["C:\\Windows\\Fonts\\simkai.ttf", "C:\\Windows\\Fonts\\simsun.ttc"]
    elif system == "Darwin":
        font_paths = ["/System/Library/Fonts/STKaiti.ttf", "/Library/Fonts/Songti.ttc"]
    font = None
    for path in font_paths:
        if os.path.exists(path):
            try: font = ImageFont.truetype(path, size); break
            except Exception: continue
    if font is None: font = ImageFont.load_default()
    return font

def create_share_card(image_bytes, cloud_name, tier, score):
    base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    target_width = 1000
    ratio = target_width / base_img.width
    image_height = int(base_img.height * ratio)
    base_img = base_img.resize((target_width, image_height), Image.Resampling.LANCZOS)

    footer_height = 350 
    total_height = image_height + footer_height
    canvas = Image.new("RGBA", (target_width, total_height), (250, 249, 246, 255))
    canvas.paste(base_img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    
    clean_tier = normalize_tier(tier)
    theme_color_hex = get_tier_color(clean_tier)
    theme_color_rgb = hex_to_rgb(theme_color_hex)
    text_color_main = (44, 62, 80)
    text_color_sub = (127, 140, 141)
    
    font_badge_abbr = load_chinese_font(100) 
    font_score_num = load_chinese_font(100) 
    font_score_label = load_chinese_font(30) 
    font_name = load_chinese_font(80)  
    font_date = load_chinese_font(30)  
    font_en = load_chinese_font(40)

    footer_start_y = image_height
    padding = 50

    draw.line([(padding, footer_start_y), (target_width - padding, footer_start_y)], fill=theme_color_rgb, width=3)
    badge_x = padding
    badge_y = footer_start_y + 55
    draw.text((badge_x, badge_y), clean_tier, fill=theme_color_rgb, font=font_badge_abbr)

    score_num_str = str(score)
    score_label_str = "分"
    score_num_width = draw.textlength(score_num_str, font=font_score_num)
    score_label_width = draw.textlength(score_label_str, font=font_score_label)
    score_x_end = target_width - padding
    draw.text((score_x_end - score_label_width, badge_y + 55), score_label_str, fill=theme_color_rgb, font=font_score_label)
    draw.text((score_x_end - score_label_width - score_num_width - 10, badge_y), score_num_str, fill=theme_color_rgb, font=font_score_num)

    name_y = footer_start_y + 180
    draw.text((padding, name_y), cloud_name, fill=text_color_main, font=font_name)
    
    en_name = CLOUD_TRANSLATIONS.get(cloud_name, "")
    if en_name:
        draw.text((padding, name_y + 100), en_name, fill=text_color_sub, font=font_en)
        footer_offset = 180
    else:
        footer_offset = 100

    date_str = datetime.datetime.now().strftime("%Y.%m.%d")
    footer_text = f"观测于 {date_str}  |  云彩收集者手册"
    draw.text((padding, name_y + footer_offset), footer_text, fill=text_color_sub, font=font_date)

    output_buffer = io.BytesIO()
    canvas.save(output_buffer, format="PNG")
    return output_buffer.getvalue()

init_db()

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except:
    st.error("请配置 GEMINI_API_KEY")
    st.stop()

# ==========================================
# 🔄 5. 侧边栏
# ==========================================
st.sidebar.markdown("## ☁️ 档案中心")
sidebar_placeholder = st.sidebar.empty()

# ✨✨✨ 工具栏重构：强制小按钮 & 并排 ✨✨✨
st.sidebar.markdown("---")
st.sidebar.caption("🔧 数据管理")
col_tool1, col_tool2 = st.sidebar.columns(2)

with col_tool1:
    with open("clouds.db", "rb") as fp:
        st.download_button(
            label="💾 备份",
            data=fp,
            file_name=f"clouds_backup.db",
            mime="application/octet-stream",
            help="下载数据库到本地"
        )

with col_tool2:
    if st.button("🛠️ 修复", help="修复显示问题"):
        count = fix_legacy_scores_forced()
        if count > 0:
            st.toast(f"已修复 {count} 条数据", icon="✅")
            time.sleep(1)
            st.rerun()
        else:
            st.toast("数据正常", icon="👌")

def process_history_data(raw_data):
    if not raw_data: return 0, 0, 0, {"UR":0,"SSR":0,"SR":0,"R":0,"N":0}, {}, set()
    cloud_map = {}
    total_score = 0
    collected_names = set()
    for row in raw_data:
        c_name = row[1]
        c_score = row[3]
        collected_names.add(c_name)
        if c_name not in cloud_map: cloud_map[c_name] = []
        cloud_map[c_name].append(row)
        total_score += c_score
    tiers_data = {"UR": {}, "SSR": {}, "SR": {}, "R": {}, "N": {}}
    tier_counts = {"UR": 0, "SSR": 0, "SR": 0, "R": 0, "N": 0}
    for c_name, records in cloud_map.items():
        best_record = max(records, key=lambda x: x[3]) 
        best_score = best_record[3]
        real_tier = calculate_tier_from_score(best_score)
        if real_tier in tiers_data:
            tiers_data[real_tier][c_name] = records
            tier_counts[real_tier] += 1
    unique_count = len(cloud_map)
    total_obs = len(raw_data)
    return total_score, total_obs, unique_count, tier_counts, tiers_data, collected_names

history_data_raw = get_history()
g_score, g_obs, g_unique, g_tier_counts, g_pokedex, g_collected_names = process_history_data(history_data_raw)

RANK_SYSTEM = [
    (0.00, "I", "抬头族", "#95a5a6"),       
    (0.05, "II", "见习观测员", "#27ae60"),  
    (0.15, "III", "天空记录者", "#2980b9"), 
    (0.30, "IV", "追风者", "#2980b9"),      
    (0.50, "V", "云图绘制师", "#8e44ad"),   
    (0.65, "VI", "苍穹之眼", "#8e44ad"),    
    (0.80, "VII", "云端领主", "#f1c40f"),   
    (0.95, "VIII", "天空守护神", "#c0392b"),
    (1.00, "IX", "气象之神", "#e74c3c")     
]

def get_user_rank_info(current_score):
    max_score = MAX_POSSIBLE_SCORE
    current_pct = current_score / max_score if max_score > 0 else 0
    
    prev_pct = 0
    for pct, roman, title, color in RANK_SYSTEM:
        target_score = int(max_score * pct)
        if current_score < target_score:
            gap = target_score - current_score
            section_progress = (current_score - (max_score * prev_pct)) / (target_score - (max_score * prev_pct))
            
            idx = RANK_SYSTEM.index((pct, roman, title, color))
            if idx > 0:
                curr_roman, curr_title, curr_color = RANK_SYSTEM[idx-1][1], RANK_SYSTEM[idx-1][2], RANK_SYSTEM[idx-1][3]
            else:
                curr_roman, curr_title, curr_color = "I", "抬头族", "#95a5a6"
            
            tooltip = f"下一级：Lv.{roman} {title} (还需 {gap} 分)"
            return curr_roman, curr_title, curr_color, section_progress, tooltip
        prev_pct = pct
        
    last = RANK_SYSTEM[-1]
    return last[1], last[2], last[3], 1.0, "已达理论极限！"

rank_roman, rank_title, rank_color, progress_val, rank_tooltip = get_user_rank_info(g_score)

def render_sidebar():
    with sidebar_placeholder.container():
        st.markdown(f"""
        <div style="background:#fff; border-radius:12px; padding:15px; margin-bottom:20px; border:1px solid #eee;">
            <div style="color:#7f8c8d; font-size:12px; margin-bottom:5px; font-family:'KaiTi',serif;">当前称号</div>
            <div class="tooltip-target" title="{rank_tooltip}" style="margin-bottom:10px; font-family:'KaiTi',serif;">
                <span style="font-size:14px; font-weight:bold; color:{rank_color}; background:rgba(0,0,0,0.05); padding:2px 6px; border-radius:4px; margin-right:5px;">Lv.{rank_roman}</span>
                <span style="font-size:20px; font-weight:bold; color:#2c3e50;">{rank_title}</span>
            </div>
            <div style="background:#ecf0f1; height:6px; border-radius:3px; overflow:hidden;">
                <div style="background:{rank_color}; width:{min(progress_val*100, 100)}%; height:100%;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:15px; font-family:'KaiTi',serif;">
                <div style="text-align:center;">
                    <div style="font-size:16px; font-weight:bold;">{g_score}</div>
                    <div style="font-size:10px; color:#95a5a6;">积分</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:16px; font-weight:bold;">{g_unique}/{len(OFFICIAL_SCORES)}</div>
                    <div style="font-size:10px; color:#95a5a6;">图鉴</div>
                </div>
                <div style="text-align:center;">
                    <div style="font-size:16px; font-weight:bold;">{g_obs}</div>
                    <div style="font-size:10px; color:#95a5a6;">快门</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<h4 style='font-family:KaiTi,serif; color:#2c3e50; margin-bottom:10px;'>🏅 荣誉勋章</h4>", unsafe_allow_html=True)
        ach_cols = st.columns(4)
        col_idx = 0
        
        for ach_name, ach_data in ACHIEVEMENTS.items():
            required = set(ach_data["clouds"])
            have_count = len(required.intersection(g_collected_names))
            missing = required - g_collected_names
            if not missing: tooltip_text = f"【已解锁】{ach_data['desc']}"
            else:
                missing_str = "、".join(list(missing)[:3])
                if len(missing) > 3: missing_str += "..."
                tooltip_text = f"【未解锁】还需收集：{missing_str}"

            is_unlocked = False
            if "2 种" in ach_data["desc"] and have_count >= 2: is_unlocked = True
            elif "3 种" in ach_data["desc"] and have_count >= 3: is_unlocked = True
            elif "1 种" in ach_data["desc"] and have_count >= 1: is_unlocked = True
            elif "集齐" in ach_data["desc"] and have_count == len(required): is_unlocked = True
            
            with ach_cols[col_idx % 4]:
                style = "opacity:1; cursor:help;" if is_unlocked else "opacity:0.2; filter:grayscale(100%); cursor:help;"
                st.markdown(f"<div style='text-align:center; {style}' title='{tooltip_text}'><div style='font-size:24px;'>{ach_data['icon']}</div></div>", unsafe_allow_html=True)
            col_idx += 1
            
        st.divider()
        st.caption("藏品统计")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown(f"<span style='color:#c0392b'>🔴 UR: {g_tier_counts['UR']}</span>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:#f1c40f'>🟡 SSR: {g_tier_counts['SSR']}</span>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:#8e44ad'>🟣 SR: {g_tier_counts['SR']}</span>", unsafe_allow_html=True)
        with col_s2:
            st.markdown(f"<span style='color:#2980b9'>🔵 R: {g_tier_counts['R']}</span>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:#7f8c8d'>⚪ N: {g_tier_counts['N']}</span>", unsafe_allow_html=True)

render_sidebar()

# ==========================================
# 🖥️ 6. 主界面 (V5.7: 修复版像素云)
# ==========================================
st.markdown("""
<div class="pixel-cloud-container">
    <img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCA2NCAzMiIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8c3R5bGU+LnB7ZmlsbDojYmRjM2M3O308L3N0eWxlPgogIDxyZWN0IHg9IjIwIiB5PSI0IiB3aWR0aD0iMjAiIGhlaWdodD0iNCIgY2xhc3M9InAiLz4KICA8cmVjdCB4PSIxMiIgeT0iOCIgd2lkdGg9IjM2IiBoZWlnaHQ9IjQiIGNsYXNzPSJwIi8+CiAgPHJlY3QgeD0iOCIgeT0iMTIiIHdpZHRoPSI0OCIgaGVpZ2h0PSI0IiBjbGFzcz0icCIvPgogIDxyZWN0IHg9IjQiIHk9IjE2IiB3aWR0aD0iNTYiIGhlaWdodD0iNCIgY2xhc3M9InAiLz4KICA8cmVjdCB4PSI4IiB5PSIyMCIgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQiIGNsYXNzPSJwIi8+Cjwvc3ZnPg==" class="pixel-cloud left">
    <div>
        <h1 style='text-align: center; margin: 0; font-family:KaiTi,serif; font-size: 3.5em;'>云彩收集者手册</h1>
    </div>
    <img src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCA2NCAzMiIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8c3R5bGU+LnB7ZmlsbDojYmRjM2M3O308L3N0eWxlPgogIDxyZWN0IHg9IjIwIiB5PSI0IiB3aWR0aD0iMjAiIGhlaWdodD0iNCIgY2xhc3M9InAiLz4KICA8cmVjdCB4PSIxMiIgeT0iOCIgd2lkdGg9IjM2IiBoZWlnaHQ9IjQiIGNsYXNzPSJwIi8+CiAgPHJlY3QgeD0iOCIgeT0iMTIiIHdpZHRoPSI0OCIgaGVpZ2h0PSI0IiBjbGFzcz0icCIvPgogIDxyZWN0IHg9IjQiIHk9IjE2IiB3aWR0aD0iNTYiIGhlaWdodD0iNCIgY2xhc3M9InAiLz4KICA8cmVjdCB4PSI4IiB5PSIyMCIgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQiIGNsYXNzPSJwIi8+Cjwvc3ZnPg==" class="pixel-cloud right">
</div>
""", unsafe_allow_html=True)

st.markdown("<p style='text-align: center; color: #7f8c8d; margin-bottom: 40px; font-family:KaiTi,serif; font-size: 1.2em;'>抬起头，收集来自天空的信笺</p>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🔭 观测台", "🏆 藏品馆"])

# === Tab 1: 智能观测 ===
with tab1:
    top_left, top_right = st.columns([1, 1])
    with top_left:
        uploaded_file = st.file_uploader(" ", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with top_right:
        st.markdown(f"""
        <div class="mini-dashboard">
            <div style="display:flex; align-items:center;">
                <div style="font-size:32px; margin-right:15px;">☁️</div>
                <div>
                    <div style="color:#7f8c8d; font-size:12px; font-family:'KaiTi',serif;">当前积分</div>
                    <div style="font-size:24px; font-weight:bold; color:#2c3e50;">{g_score}</div>
                </div>
            </div>
            <div style="text-align:right;">
                <div style="color:#7f8c8d; font-size:12px; font-family:'KaiTi',serif;">本次等级</div>
                <div style="font-size:16px; font-weight:bold; color:{rank_color}; font-family:'KaiTi',serif;">{rank_title}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    main_left, main_right = st.columns([1, 1])
    
    image_bytes = None
    existing_record = None
    
    if uploaded_file:
        image_bytes = uploaded_file.getvalue()
        md5_hash = hashlib.md5(image_bytes).hexdigest()
        existing_record = get_record_by_hash(md5_hash)

    with main_left:
        if uploaded_file:
            b64_img = image_to_base64(image_bytes)
            st.markdown(f"""
            <div class="apple-card">
                <div class="preview-container">
                    <img src="{b64_img}">
                </div>
                <div style="text-align:center; color:#7f8c8d; font-size:12px; margin-top:10px; font-family:sans-serif;">
                    {uploaded_file.name}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            action_placeholder = st.empty()
            should_process = False
            if not existing_record:
                if action_placeholder.button("⚡ 鉴定这朵云", type="primary", use_container_width=True):
                    should_process = True
        else:
            st.markdown("""
            <div class="apple-card" style="justify-content: center; align-items: center; text-align: center;">
                <div style="font-size: 60px; margin-bottom: 20px; opacity: 0.3;">☁️</div>
                <h3 style="color:#2c3e50; margin-bottom: 10px; font-family:'KaiTi',serif;">准备就绪</h3>
                <p style="color:#95a5a6; font-family:'KaiTi',serif;">请上传一张天空的照片</p>
            </div>
            """, unsafe_allow_html=True)

    if 'should_process' in locals() and should_process and uploaded_file:
        with main_right:
             status_container = st.empty()
             status_container.info("⏳ 卫星正在解析云层结构...")
        
        try:
            # === 🛡️ 第一道防线：检查文件大小 ===
            if len(image_bytes) < 100:
                status_container.empty()
                st.error("🚫 上传失败：图片数据为空 (0KB)。请尝试重新上传，或换一张照片。")
                st.stop()

            # === 🛡️ 第二道防线：尝试智能解码 ===
            try:
                # 尝试直接打开
                image_obj = Image.open(io.BytesIO(image_bytes))
                
                # 针对“披着JPG皮的WebP/HEIC”进行强制转换
                if image_obj.format not in ["JPEG", "PNG", "WEBP"]:
                    image_obj = image_obj.convert("RGB")
                    
            except Exception:
                # 如果标准库打不开，提示用户可能是 HEIC 或特殊格式
                status_container.empty()
                st.error("🚫 无法读取此图片格式。")
                st.info("💡 建议：\n1. 请尝试 **“截图”** 这张照片，然后上传截图（截图兼容性 100%）。\n2. 或在相册里编辑一下保存后再上传。")
                st.stop()
            client = genai.Client(api_key=api_key)
            
            prompt = """
            任务：识别图片中的云彩。
            第一步：判断这张图片是否包含云彩或天空现象。
            - 如果是猫、狗、室内、黑屏、文字截图等非天空图片，返回 {"is_cloud": false}
            - 如果包含云，返回 {"is_cloud": true, ...}
            
            第二步：如果是云，请进行分类。
            返回 JSON 格式：
            {
                "is_cloud": true/false,
                "cloud_name": "标准学术名称(中文，如：积云、高积云、波状高积云)", 
                "score_suggestion": 估算分数(10-100),
                "science_fact": "科普(30字内)",
                "weather_tip": "预告(20字内)"
            }
            """
            
            response = None
            success = False
            
            for model_name in AVAILABLE_MODELS:
                if success: break
                for attempt in range(2): 
                    try:
                        if attempt > 0 or model_name != AVAILABLE_MODELS[0]:
                            status_container.warning(f"📡 信号微弱，切换频率至 {model_name}...")
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[prompt, image_obj], 
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        success = True
                        break
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str or "503" in err_str:
                            time.sleep(2)
                            continue
                        else: break 

            if not success or not response:
                raise Exception("卫星连接暂时中断，请稍后再试。")

            import json
            result = json.loads(response.text)
            
            if not result.get("is_cloud", False):
                status_container.empty()
                st.error("🚫 鉴定失败：画面中未发现明显云彩结构。")
            else:
                c_name = result.get("cloud_name", "未知")
                ai_score = result.get("score_suggestion", 10)
                c_sci = result.get("science_fact", "暂无")
                c_wea = result.get("weather_tip", "暂无")
                
                official_score = get_official_score(c_name, ai_score)
                calculated_tier = calculate_tier_from_score(official_score)
                is_new = not check_cloud_discovered(c_name)
                final_score = official_score if is_new else 0
                
                save_to_db(c_name, calculated_tier, final_score, c_sci, c_wea, image_bytes, md5_hash)
                st.rerun()
                
        except Exception as e:
            status_container.empty()
            if "429" in str(e): st.error("🔒 观测次数过多，请休息片刻。")
            else: st.error(f"中断: {e}")

    with main_right:
        if existing_record:
            r_name, r_tier, r_score, r_sci, r_wea, r_time = existing_record
            display_score = r_score if r_score > 0 else get_official_score(r_name, 10)
            display_tier = calculate_tier_from_score(display_score)
            color = get_tier_color(display_tier)
            score_html = f"+{r_score}" if r_score > 0 else "<span style='color:#95a5a6; font-size:20px'>+0 (备份)</span>"
            title_tag = f"✨ 发现：{r_name}" if r_score > 0 else f"📷 档案：{r_name}"
            
            bilingual_title_html = get_bilingual_name(r_name)
            
            st.markdown(f"""
            <div class="apple-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h1 style="color:{color}; font-size:64px; margin:0; font-family:'Lora',serif;">{display_tier}</h1>
                    <div style="text-align:right;">
                        <span style="font-size:14px; color:#95a5a6; font-family:'KaiTi',serif;">获得积分</span><br>
                        <span style="font-size:32px; font-weight:bold; color:{color}; font-family:'Lora',serif;">{score_html}</span>
                    </div>
                </div>
                <h2 style="margin-top:10px; font-size: 28px; font-family:'KaiTi',serif;">✨ {bilingual_title_html}</h2>
                <hr style="border:0; border-top:1px solid rgba(0,0,0,0.05); margin:25px 0;">
                <div style="display:flex; gap:20px; flex-grow: 1;">
                    <div style="flex:1; background:rgba(245,245,247,0.5); padding:20px; border-radius:8px; border-left:4px solid #bdc3c7;">
                        <strong style="color:#2c3e50; font-family:'KaiTi',serif;">📜 博物志</strong><br><span style="color:#34495e; font-size:15px; line-height:1.6; font-family:'KaiTi',serif;">{r_sci}</span>
                    </div>
                    <div style="flex:1; background:rgba(255,244,229,0.5); padding:20px; border-radius:8px; border-left:4px solid #f39c12;">
                        <strong style="color:#d35400; font-family:'KaiTi',serif;">🌦️ 天气签</strong><br><span style="color:#34495e; font-size:15px; line-height:1.6; font-family:'KaiTi',serif;">{r_wea}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            card_bytes = create_share_card(image_bytes, r_name, display_tier, r_score if r_score > 0 else display_score)
            st.download_button("✨ 获取收藏卡片", card_bytes, file_name=f"Card_{r_name}.png", mime="image/png", type="primary", use_container_width=True)

        elif not uploaded_file:
             st.markdown('<div class="apple-card" style="display: flex; align-items: center; justify-content: center; color: #ccc;"><h3>等待左侧影像...</h3></div>', unsafe_allow_html=True)

# === Tab 2: 🏆 藏品馆 ===
with tab2:
    if not history_data_raw:
        st.markdown('<div class="apple-card" style="text-align:center; color:#95a5a6; padding:50px; font-family:KaiTi,serif;">📦<br>暂无藏品，去观测台开始探索吧</div>', unsafe_allow_html=True)
    else:
        for tier in ["UR", "SSR", "SR", "R", "N"]:
            clouds_in_tier = g_pokedex[tier]
            if clouds_in_tier:
                color = get_tier_color(tier)
                st.markdown(f"<h3 style='color:{color}; border-bottom:1px dashed {color}; padding-bottom:5px; margin-top:30px; display:flex; align-items:center; font-family:KaiTi,serif;'><span style='font-size:24px; margin-right:10px; font-family:Lora,serif;'>{tier}</span> 级图鉴</h3>", unsafe_allow_html=True)
                cols = st.columns(4)
                for idx, (c_name, items) in enumerate(clouds_in_tier.items()):
                    with cols[idx % 4]:
                        latest_item = items[0]
                        img_blob = latest_item[6]
                        science_fact = latest_item[4]
                        thumb = make_square_thumbnail(img_blob)
                        st.image(thumb, use_container_width=True)
                        
                        pop_title = f"{c_name} ({len(items)})"
                        with st.popover(pop_title, use_container_width=True):
                            st.markdown(f"### {get_bilingual_name(c_name)}", unsafe_allow_html=True)
                            st.info(f"📜 {science_fact}")
                            st.markdown("#### 📸 历史记录")
                            
                            for item in items:
                                i_id = item[0]
                                i_blob = item[6]
                                i_score = item[3]
                                i_time = item[8]
                                i_img = Image.open(io.BytesIO(i_blob))
                                st.image(i_img, use_container_width=True)
                                
                                col_desc, col_del = st.columns([3, 1])
                                with col_desc:
                                    st.caption(f"{i_time[:16]} | 积分 +{i_score}")
                                with col_del:
                                    del_key = f"del_{i_id}"
                                    if not st.session_state.get(del_key, False):
                                        if st.button("🗑️", key=f"btn_del_{i_id}", help="删除此记录"):
                                            st.session_state[del_key] = True
                                            st.rerun()
                                    else:
                                        st.markdown("Confirm?")
                                        if st.button("✔️", key=f"btn_yes_{i_id}", type="primary"):
                                            delete_record(i_id)
                                            del st.session_state[del_key]
                                            st.rerun()
                                        if st.button("❌", key=f"btn_no_{i_id}"):
                                            del st.session_state[del_key]
                                            st.rerun()
                                st.divider()