import streamlit as st
import json
import os
import hashlib
import copy
import time
# 假设你的核心逻辑在这个文件里，且接口保持一致
from logic import WorkplaceOptimizer

# ==========================================
# 0. 样式与配置
# ==========================================
st.set_page_config(page_title="MAA 基建排班售后服务", page_icon="💎", layout="wide")

st.markdown("""
    <style>
    /* 隐藏顶部菜单 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppHeader {display: none;}

    /* 简单的卡片样式 */
    .user-card {
        padding: 20px;
        background-color: #f0f2f6;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    /* ===== 强制隐藏右上角 GitHub 图标（绝对生效版） ===== */

    /* 核心按钮容器 */
    .stAppHeader .stToolbarActions .stToolbarActionButton button {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }
    
    /* 为防止版本变动，连父级也一起隐藏 */
    .stAppHeader .stToolbarActions .stToolbarActionButton {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }
    
    /* 某些版本中该按钮会有 data-testid：stToolbarActionButtonIcon */
    [data-testid="stToolbarActionButtonIcon"] {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }
    
    /* 完全移除容器占位空间 */
    .stAppHeader .stToolbarActions {
        gap: 0 !important;
    }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 1. 工具函数
# ==========================================
def get_user_hash(order_id):
    return hashlib.sha256(order_id.strip().encode('utf-8')).hexdigest()[:16]


def load_user_data(user_hash):
    base_path = os.path.join("user_data", user_hash)
    ops_path = os.path.join(base_path, "operators.json")
    conf_path = os.path.join(base_path, "config.json")

    if os.path.exists(ops_path) and os.path.exists(conf_path):
        with open(ops_path, 'r', encoding='utf-8') as f:
            ops = json.load(f)
        with open(conf_path, 'r', encoding='utf-8') as f:
            conf = json.load(f)
        return ops, conf
    return None, None


def save_user_data(user_hash, ops_data):
    """将修改后的干员数据永久保存到磁盘"""
    base_path = os.path.join("user_data", user_hash)
    ops_path = os.path.join(base_path, "operators.json")

    # 确保目录存在（防止意外删除）
    if os.path.exists(base_path):
        with open(ops_path, 'w', encoding='utf-8') as f:
            json.dump(ops_data, f, ensure_ascii=False, indent=2)
        return True
    return False


# 模拟练度提升的函数
def upgrade_operator_in_memory(operators_data, char_id, target_phase, target_level):
    """在内存中修改干员练度"""
    for op in operators_data:
        if op['id'] == char_id:
            # 简单的逻辑：如果当前练度低于目标，则直接修改为目标
            # 注意：实际 operators.json 结构可能更复杂 (skill, mod等)，需按需调整
            op['phase'] = max(op.get('phase', 0), target_phase)
            op['level'] = max(op.get('level', 0), target_level)
            return True
    return False


def clean_data(d):
    # 过滤掉 'raw_results' 这样包含复杂对象的键
    return {k: v for k, v in d.items() if k != 'raw_results'}


# ==========================================
# 2. 会话状态初始化
# ==========================================
if 'auth_status' not in st.session_state:
    st.session_state.auth_status = False
if 'user_hash' not in st.session_state:
    st.session_state.user_hash = ""
if 'user_ops' not in st.session_state:
    st.session_state.user_ops = None  # 原始数据
if 'current_ops' not in st.session_state:
    st.session_state.current_ops = None  # 修改后的数据
if 'user_conf' not in st.session_state:
    st.session_state.user_conf = None
if 'suggestions' not in st.session_state:
    st.session_state.suggestions = []
if 'applied_upgrades' not in st.session_state:
    st.session_state.applied_upgrades = set()  # 记录用户勾选了哪些ID

# ==========================================
# 3. 登录页 (Authentication)
# ==========================================
if not st.session_state.auth_status:
    st.columns([1, 2, 1])[1].image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Arknights_logo.svg/1200px-Arknights_logo.svg.png",
        width=200)  # 示例Logo

    st.markdown("<h2 style='text-align: center;'>💎 VIP 基建售后服务</h2>", unsafe_allow_html=True)
    st.info("本服务仅供闲鱼购买用户使用，请输入您的订单号进行验证。")

    with st.form("login_form"):
        order_id = st.text_input("请输入闲鱼订单号", placeholder="例如：36281xxxxxx")
        submitted = st.form_submit_button("验证身份", use_container_width=True)

        if submitted and order_id:
            u_hash = get_user_hash(order_id)
            ops, conf = load_user_data(u_hash)

            if ops and conf:
                st.session_state.auth_status = True
                st.session_state.user_hash = u_hash
                st.session_state.user_ops = ops
                st.session_state.current_ops = copy.deepcopy(ops)  # 初始化当前练度副本
                st.session_state.user_conf = conf
                st.toast("✅ 验证成功！", icon="🎉")
                st.rerun()
            else:
                st.error("❌ 未找到订单信息或服务已过期，请联系卖家。")

# ==========================================
# 4. 主功能区
# ==========================================
else:
    # 侧边栏信息
    with st.sidebar:
        st.success(f"已登录")
        # 截取哈希前6位展示，保护隐私
        st.caption(f"ID: {st.session_state.user_hash[:6]}...")
        st.caption(f"Config: {st.session_state.user_conf.get('desc', 'Custom')}")
        if st.button("退出登录"):
            # 清除所有 Session 状态
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    st.title("🏭 智能排班生成器")

    # --- 步骤 1: 生成建议 (如果不使用缓存，每次进来先算一遍) ---
    if not st.session_state.suggestions:
        with st.status("正在分析您的基建潜力...", expanded=True) as status:
            st.write("📥 加载基础数据...")

            temp_ops_path = f"temp_{st.session_state.user_hash}.json"
            temp_conf_path = f"temp_conf_{st.session_state.user_hash}.json"

            # 写入临时文件供 logic.py 读取
            with open(temp_ops_path, "w", encoding='utf-8') as f:
                json.dump(st.session_state.user_ops, f)
            with open(temp_conf_path, "w", encoding='utf-8') as f:
                json.dump(st.session_state.user_conf, f)

            st.write("🧠 运行差异算法...")
            try:
                optimizer = WorkplaceOptimizer("efficiency.json", temp_ops_path, temp_conf_path)

                # 计算当前和极限
                curr = optimizer.get_optimal_assignments(ignore_elite=False)
                pot = optimizer.get_optimal_assignments(ignore_elite=True)

                # 获取升级建议
                upgrades = optimizer.calculate_upgrade_requirements(curr, pot)
                st.session_state.suggestions = upgrades

                status.update(label="分析完成", state="complete", expanded=False)

            except Exception as e:
                status.update(label="❌ 计算出错", state="error")
                st.error(f"算法错误: {str(e)}")
                st.stop()
            finally:
                # 清理临时文件
                if os.path.exists(temp_ops_path): os.remove(temp_ops_path)
                if os.path.exists(temp_conf_path): os.remove(temp_conf_path)

    # --- 步骤 2: 交互式练度确认 ---
    st.markdown("### 1. 练度补全确认")
    st.info("系统检测到您的部分干员提升练度后可大幅增加效率。**勾选并点击生成后，系统将自动记录您的练度提升。**")

    # 用于收集用户勾选的 upgrading items
    # 注意：我们不能直接在这里修改 user_ops，要在按钮点击后修改

    # 容器布局
    cols = st.columns(2)

    # 使用字典来存储用户的勾选状态，方便后续处理
    selected_upgrades_indices = []

    if not st.session_state.suggestions:
        st.success("🎉 完美！您当前的练度已达到该布局的理论极限，无需额外提升。")
    else:
        with st.container(border=True):
            st.write("👇 **请勾选您已完成（或计划立即完成）的提升：**")

            # 遍历建议生成 Checkbox
            for idx, item in enumerate(st.session_state.suggestions):
                col = cols[idx % 2]

                # --- 核心修改：保持文本一致性 ---
                # 假设 item['gain'] 是小数 (如 0.05 代表 5%)，这里乘以 100
                gain_pct = item['gain'] * 100

                if item.get('type') == 'bundle':
                    op_names = "+".join([o['name'] for o in item['ops']])
                    # 标签格式
                    label = f"【组合】{op_names} (效率 +{gain_pct:.1f}%)"
                    # 鼠标悬浮提示
                    help_txt = "\n".join([f"{o['name']}: 精{o['current']} -> 精{o['target']}" for o in item['ops']])
                else:
                    label = f"【单人】{item['name']} (效率 +{gain_pct:.1f}%)"
                    help_txt = f"当前: 精{item['current']} -> 目标: 精{item['target']}"

                # 渲染 Checkbox
                s_key = f"suggest_{idx}"
                if col.checkbox(label, key=s_key, help=help_txt):
                    selected_upgrades_indices.append(idx)

    # --- 步骤 3: 生成最终排班 & 保存数据 ---
    st.markdown("### 2. 获取排班表")

    action_col, _ = st.columns([1, 2])

    if action_col.button("🚀 保存练度并生成排班", type="primary", use_container_width=True):

        with st.spinner("正在保存练度并重新演算..."):

            # === A. 核心修改：修改内存数据并保存到文件 ===

            # 1. 复制一份当前的基础数据
            # 注意：我们基于 st.session_state.user_ops (原始数据) 进行修改
            new_ops_data = copy.deepcopy(st.session_state.user_ops)
            data_changed = False

            # 2. 应用所有勾选的提升
            for idx in selected_upgrades_indices:
                item = st.session_state.suggestions[idx]

                if item.get('type') == 'bundle':
                    for o in item['ops']:
                        # 注意：确保 item['ops'] 里有 id 字段，如果没有请检查 logic.py
                        if upgrade_operator_in_memory(new_ops_data, o.get('id'), o['target'], 1):
                            data_changed = True
                else:
                    if upgrade_operator_in_memory(new_ops_data, item.get('id'), item['target'], 1):
                        data_changed = True

            # 3. 如果有数据变动，写入硬盘 (Persistent Save)
            if data_changed:
                try:
                    save_user_data(st.session_state.user_hash, new_ops_data)
                    st.toast("✅ 练度信息已更新并保存！", icon="💾")

                    # 4. 关键：更新 Session State，这样下次计算就基于新数据了
                    st.session_state.user_ops = new_ops_data

                    # 可选：如果希望下次进来不再显示这些建议，可以清空 suggestions
                    # 但为了不让页面突然闪动，本次先保留显示，或者可以设为 [] 强制下次重算
                    # st.session_state.suggestions = []
                except Exception as e:
                    st.error(f"保存数据失败: {e}")
                    st.stop()

            # === B. 进行排班计算 (使用更新后的 new_ops_data) ===

            run_ops_path = f"run_ops_{st.session_state.user_hash}.json"
            run_conf_path = f"run_conf_{st.session_state.user_hash}.json"

            with open(run_ops_path, "w", encoding='utf-8') as f:
                json.dump(new_ops_data, f)  # 使用最新的数据
            with open(run_conf_path, "w", encoding='utf-8') as f:
                json.dump(st.session_state.user_conf, f)

            # 运行计算
            optimizer = WorkplaceOptimizer("efficiency.json", run_ops_path, run_conf_path)
            # ignore_elite=False: 此时 new_ops_data 已经是提升后的练度了，所以按实际练度算即可
            final_result = optimizer.get_optimal_assignments(ignore_elite=False)

            # === C. 结果处理 ===

            # 清理临时文件
            if os.path.exists(run_ops_path): os.remove(run_ops_path)
            if os.path.exists(run_conf_path): os.remove(run_conf_path)

            # 提取效率
            raw_res = final_result.get('raw_results', [])
            current_efficiency = raw_res[0].total_efficiency if raw_res else 0
            st.session_state.final_eff = current_efficiency

            # 清洗并生成 JSON
            cleaned_result = clean_data(final_result)
            st.session_state.final_result_json = json.dumps(cleaned_result, ensure_ascii=False, indent=2)

            st.balloons()

    # 结果展示区 (保持不变)
    if 'final_result_json' in st.session_state:
        st.markdown("---")
        r_col1, r_col2 = st.columns([1, 1])

        with r_col1:
            st.metric("预计最终效率", f"{st.session_state.final_eff:.2f}%")
            st.download_button(
                label="📥 下载 MAA 排班文件 (JSON)",
                data=st.session_state.final_result_json,
                file_name="maa_schedule_optimized.json",
                mime="application/json",
                use_container_width=True
            )

        with r_col2:
            st.info("""
            **使用说明：**
            1. 下载 JSON 文件。
            2. 打开 MAA -> 基建换班。
            3. 选择 "自定义排班" 并导入该文件。
            """)