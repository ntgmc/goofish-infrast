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
        st.caption(f"Config: {st.session_state.user_conf.get('desc', 'Custom')}")
        if st.button("退出登录"):
            st.session_state.auth_status = False
            st.rerun()

    st.title("🏭 智能排班生成器")

    # --- 步骤 1: 生成建议 (如果不使用缓存，每次进来先算一遍) ---
    # 为了性能，我们在第一次加载时计算建议
    if not st.session_state.suggestions:
        with st.status("正在分析您的基建潜力...", expanded=True) as status:
            st.write("📥 加载基础数据...")
            # 保存临时文件供 logic.py 读取 (假设你的库读取文件路径)
            temp_ops_path = f"temp_{st.session_state.user_hash}.json"
            temp_conf_path = f"temp_conf_{st.session_state.user_hash}.json"

            with open(temp_ops_path, "w", encoding='utf-8') as f:
                json.dump(st.session_state.user_ops, f)
            with open(temp_conf_path, "w", encoding='utf-8') as f:
                json.dump(st.session_state.user_conf, f)

            st.write("🧠 运行差异算法...")
            # 初始化优化器
            optimizer = WorkplaceOptimizer("efficiency.json", temp_ops_path, temp_conf_path)

            # 计算当前和极限
            curr = optimizer.get_optimal_assignments(ignore_elite=False)
            pot = optimizer.get_optimal_assignments(ignore_elite=True)

            # 获取升级建议
            upgrades = optimizer.calculate_upgrade_requirements(curr, pot)
            st.session_state.suggestions = upgrades

            # 清理
            if os.path.exists(temp_ops_path): os.remove(temp_ops_path)
            if os.path.exists(temp_conf_path): os.remove(temp_conf_path)

            status.update(label="分析完成", state="complete", expanded=False)

    # --- 步骤 2: 交互式练度确认 ---
    st.markdown("### 1. 练度补全确认")
    st.info(
        "系统检测到您的部分干员提升练度后可大幅增加效率。如果您已经完成了某些提升（或愿意为了排班去提升），请在下方勾选，系统将基于**勾选后的新练度**生成排班。")

    # 将建议转换为复选框
    # 注意：这里需要处理状态保持，Streamlit 的 checkbox 每次 rerun 会重置，除非绑定 key

    cols = st.columns(2)
    has_changes = False

    # 创建一个临时的操作员列表副本用于本次计算
    temp_working_ops = copy.deepcopy(st.session_state.user_ops)

    if not st.session_state.suggestions:
        st.success("🎉 完美！您当前的练度已达到该布局的理论极限，无需额外提升。")
    else:
        with st.container(border=True):
            st.write("👇 **请勾选您已完成（或计划立即完成）的提升：**")

            for idx, item in enumerate(st.session_state.suggestions):
                # 构造唯一的key
                s_key = f"s_{idx}"

                # 构造显示文本
                if item.get('type') == 'bundle':
                    op_names = "+".join([o['name'] for o in item['ops']])
                    label = f"【组合】{op_names} (效率 +{item['gain']:.1f}%)"
                    help_txt = "\n".join([f"{o['name']}: 精{o['current']} -> 精{o['target']}" for o in item['ops']])
                else:
                    label = f"【单人】{item['name']} (效率 +{item['gain']:.1f}%)"
                    help_txt = f"当前: 精{item['current']} -> 目标: 精{item['target']}"

                # 渲染 Checkbox
                # 默认值逻辑：如果之前勾选过，保持勾选
                is_checked = st.checkbox(label, key=s_key, help=help_txt)

                if is_checked:
                    has_changes = True
                    # 更新 temp_working_ops
                    if item.get('type') == 'bundle':
                        for o in item['ops']:
                            # 注意：这里需要根据你的 logic.py 返回的数据结构来匹配 ID
                            # 假设 item['ops'] 里包含 id 或者 name
                            # 实际项目中建议 item 包含 char_id
                            upgrade_operator_in_memory(temp_working_ops, o.get('id'), o['target'], 1)  # 假设精2 1级
                    else:
                        upgrade_operator_in_memory(temp_working_ops, item.get('id'), item['target'], 1)

    # --- 步骤 3: 生成最终排班 ---
    st.markdown("### 2. 获取排班表")

    action_col, _ = st.columns([1, 2])

    if action_col.button("🚀 生成最新排班方案", type="primary", use_container_width=True):

        with st.spinner("正在基于您的选择重新演算..."):
            # 1. 保存包含了用户勾选练度的临时文件
            run_ops_path = f"run_ops_{st.session_state.user_hash}.json"
            run_conf_path = f"run_conf_{st.session_state.user_hash}.json"

            with open(run_ops_path, "w", encoding='utf-8') as f:
                json.dump(temp_working_ops, f)
            with open(run_conf_path, "w", encoding='utf-8') as f:
                json.dump(st.session_state.user_conf, f)

            # 2. 运行计算
            optimizer = WorkplaceOptimizer("efficiency.json", run_ops_path, run_conf_path)
            final_result = optimizer.get_optimal_assignments(ignore_elite=False)  # 注意这里是 False，因为我们要基于(原始+勾选)的练度算

            # 3. 清理
            if os.path.exists(run_ops_path): os.remove(run_ops_path)
            if os.path.exists(run_conf_path): os.remove(run_conf_path)

            # 4. 展示结果
            st.session_state.final_result_json = json.dumps(final_result, ensure_ascii=False, indent=2)
            st.session_state.final_eff = \
            final_result.get('raw_results', [type('obj', (object,), {'total_efficiency': 0})])[
                0].total_efficiency if 'raw_results' in final_result else 0

            st.balloons()

    # 结果展示区
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

    # --- 可选：保存偏好 (localStorage 模拟) ---
    # Streamlit 原生不支持直接存 Cookie，但可以通过 query params 稍微取巧
    # 或者如果不要求严格，依靠 session state 已经足够用户在不关闭页面的情况下反复调整