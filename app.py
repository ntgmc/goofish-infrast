import streamlit as st
import json
import os
import hashlib
import copy
import time

# 假设核心逻辑文件
from logic import WorkplaceOptimizer

# ==========================================
# 0. 样式与配置
# ==========================================

st.set_page_config(page_title="MAA 基建排班售后服务", page_icon="💎", layout="wide")

st.markdown("""
<style>
/* 隐藏顶部菜单和页脚 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stAppHeader {display: none;}

/* 卡片样式 */
.user-card {
    padding: 20px;
    background-color: #f0f2f6;
    border-radius: 10px;
    margin-bottom: 20px;
}

/* 强制隐藏右上角 */
.stAppHeader .stToolbarActions .stToolbarActionButton button,
[data-testid="stToolbarActionButtonIcon"],
.stAppHeader .stToolbarActions {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
    gap: 0 !important;
}

/* 优化按钮样式 */
div.stButton > button:first-child {
    font-weight: bold;
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
    base_path = os.path.join("user_data", user_hash)
    ops_path = os.path.join(base_path, "operators.json")

    if os.path.exists(base_path):
        with open(ops_path, 'w', encoding='utf-8') as f:
            json.dump(ops_data, f, ensure_ascii=False, indent=2)
        return True
    return False


def upgrade_operator_in_memory(operators_data, char_id, char_name, target_elite):
    """内存修改干员练度"""
    target_id_str = str(char_id)
    for op in operators_data:
        current_id_str = str(op.get('id', ''))
        current_name = op.get('name', '')

        match = False
        if current_id_str and current_id_str == target_id_str:
            match = True
        elif current_name and current_name == char_name:
            match = True

        if match:
            op['elite'] = int(target_elite)
            op['level'] = 1  # 默认重置为1级，根据需求调整
            return True, f"{current_name}"

    return False, None


def clean_data(d):
    return {k: v for k, v in d.items() if k != 'raw_results'}


# ==========================================
# 2. 会话状态初始化
# ==========================================

if 'auth_status' not in st.session_state:
    st.session_state.auth_status = False
if 'user_hash' not in st.session_state:
    st.session_state.user_hash = ""
if 'user_ops' not in st.session_state:
    st.session_state.user_ops = None
if 'user_conf' not in st.session_state:
    st.session_state.user_conf = None
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'suggestions' not in st.session_state:
    st.session_state.suggestions = []
if 'final_result_ready' not in st.session_state:
    st.session_state.final_result_ready = False

# ==========================================
# 3. 登录页
# ==========================================

if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        # st.image(
        #     "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Arknights_logo.svg/1200px-Arknights_logo.svg.png",
        #     width=150)
        st.markdown("<h2 style='text-align: center;'>💎 VIP 基建售后服务</h2>", unsafe_allow_html=True)

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
                    st.session_state.user_conf = conf
                    st.toast("✅ 验证成功！", icon="🎉")
                    st.rerun()
                else:
                    st.error("❌ 未找到订单信息或服务已过期，请联系卖家。")

# ==========================================
# 4. 主功能区
# ==========================================

else:
    # --- 侧边栏 ---
    with st.sidebar:
        st.success(f"状态: 已登录")
        st.caption(f"ID: {st.session_state.user_hash[:8]}...")
        st.caption(f"配置: {st.session_state.user_conf.get('desc', 'Custom')}")

        st.divider()
        if st.button("退出登录", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.title("🏭 智能排班生成器")

    # --- 逻辑控制区 ---

    # 临时文件路径定义
    temp_ops_path = f"temp_{st.session_state.user_hash}.json"
    temp_conf_path = f"temp_conf_{st.session_state.user_hash}.json"

    # 1. 自动运行分析 (如果是首次加载或数据已更新)
    if not st.session_state.analysis_done:
        with st.status("正在分析基建潜力...", expanded=True) as status:
            try:
                # 写入临时文件供算法读取
                with open(temp_ops_path, "w", encoding='utf-8') as f:
                    json.dump(st.session_state.user_ops, f)
                with open(temp_conf_path, "w", encoding='utf-8') as f:
                    json.dump(st.session_state.user_conf, f)

                # 调用核心算法
                optimizer = WorkplaceOptimizer("efficiency.json", temp_ops_path, temp_conf_path)
                curr = optimizer.get_optimal_assignments(ignore_elite=False)
                pot = optimizer.get_optimal_assignments(ignore_elite=True)
                upgrades = optimizer.calculate_upgrade_requirements(curr, pot)

                st.session_state.suggestions = upgrades
                st.session_state.analysis_done = True
                status.update(label="✅ 分析完成", state="complete", expanded=False)

                # 分析完成后刷新显示
                st.rerun()

            except Exception as e:
                status.update(label="❌ 分析出错", state="error")
                st.error(f"算法错误: {str(e)}")
                st.stop()
            finally:
                if os.path.exists(temp_ops_path): os.remove(temp_ops_path)
                if os.path.exists(temp_conf_path): os.remove(temp_conf_path)

    # 2. 如果已有结果，优先展示下载区 (放在顶部更方便)
    if st.session_state.get('final_result_ready', False):
        st.markdown("### 🎉 排班表已生成")
        result_container = st.container(border=True)
        with result_container:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.metric("预计最终效率", f"{st.session_state.final_eff:.2f}")
            with c2:
                st.download_button(
                    label="📥 下载 MAA 排班 JSON",
                    data=st.session_state.final_result_json,
                    file_name="maa_schedule_optimized.json",
                    mime="application/json",
                    type="primary",
                    use_container_width=True
                )
            st.caption("注：此文件包含您刚才勾选并应用的练度修改。")

    # 3. 练度建议交互区
    st.markdown("### 🛠️ 练度优化建议")

    if not st.session_state.suggestions:
        st.info("✨ 当前练度已满足该配置的理论最优解，无需额外提升。")
        # 即使没有建议，也提供生成按钮，用于生成当前练度的排班
        st.session_state.suggestions = []
    else:
        st.write(f"检测到 **{len(st.session_state.suggestions)}** 项可提升效率的优化点：")

    # 表单区域
    with st.form("upgrade_form"):
        selected_indices = []

        # 如果有建议，渲染多选框
        if st.session_state.suggestions:
            cols = st.columns(2)
            for idx, item in enumerate(st.session_state.suggestions):
                col = cols[idx % 2]
                gain_val = item['gain']

                if item.get('type') == 'bundle':
                    op_names = "+".join([o['name'] for o in item['ops']])
                    label = f"**{op_names}** (效率 +{gain_val:.2f}%)"
                    help_txt = "\n".join([f"{o['name']}: 精{o['current']} -> 精{o['target']}" for o in item['ops']])
                else:
                    label = f"**{item['name']}** (效率 +{gain_val:.2f}%)"
                    help_txt = f"当前: 精{item['current']} -> 目标: 精{item['target']}"

                if col.checkbox(label, key=f"s_{idx}", help=help_txt):
                    selected_indices.append(idx)

        st.markdown("---")
        # 按钮：生成
        generate_btn = st.form_submit_button("🚀 应用选中修改并生成排班", type="primary", use_container_width=True)

    # 4. 处理生成逻辑
    if generate_btn:
        with st.spinner("正在写入数据并重新演算..."):
            # A. 复制当前数据
            new_ops_data = copy.deepcopy(st.session_state.user_ops)
            modified_names = []

            # B. 应用勾选的修改
            for idx in selected_indices:
                item = st.session_state.suggestions[idx]
                if item.get('type') == 'bundle':
                    for o in item['ops']:
                        suc, name = upgrade_operator_in_memory(new_ops_data, o.get('id'), o.get('name'), o['target'])
                        if suc: modified_names.append(name)
                else:
                    suc, name = upgrade_operator_in_memory(new_ops_data, item.get('id'), item.get('name'),
                                                           item['target'])
                    if suc: modified_names.append(name)

            # C. 保存到硬盘 (持久化)
            if modified_names:
                save_success = save_user_data(st.session_state.user_hash, new_ops_data)
                if not save_success:
                    st.error("保存数据失败，请联系管理员")
                    st.stop()
                st.session_state.user_ops = new_ops_data  # 更新内存

            # D. 生成最终排班
            run_ops_path = f"run_ops_{st.session_state.user_hash}.json"
            run_conf_path = f"run_conf_{st.session_state.user_hash}.json"

            try:
                with open(run_ops_path, "w", encoding='utf-8') as f:
                    json.dump(new_ops_data, f, ensure_ascii=False)
                with open(run_conf_path, "w", encoding='utf-8') as f:
                    json.dump(st.session_state.user_conf, f, ensure_ascii=False)

                optimizer = WorkplaceOptimizer("efficiency.json", run_ops_path, run_conf_path)
                final_res = optimizer.get_optimal_assignments(ignore_elite=False)  # 使用新练度计算

                # 提取结果
                raw_res = final_res.get('raw_results', [])
                st.session_state.final_eff = raw_res[0].total_efficiency if raw_res else 0
                st.session_state.final_result_json = json.dumps(clean_data(final_res), ensure_ascii=False, indent=2)

                # E. 状态更新与重载
                st.session_state.final_result_ready = True

                # 关键：清除分析缓存，促使下次渲染时重新分析 (这样已应用的建议就会消失)
                st.session_state.analysis_done = False
                st.session_state.suggestions = []

                # 提示成功并重载页面
                if modified_names:
                    st.toast(f"✅ 已更新 {len(modified_names)} 位干员练度！", icon="💾")
                else:
                    st.toast("✅ 排班生成成功！", icon="📄")

                time.sleep(0.5)  # 稍作停顿让 Toast 显示
                st.rerun()  # <--- 自动刷新，替代 F5

            except Exception as e:
                st.error(f"计算发生错误: {e}")
            finally:
                if os.path.exists(run_ops_path): os.remove(run_ops_path)
                if os.path.exists(run_conf_path): os.remove(run_conf_path)