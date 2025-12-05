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


def upgrade_operator_in_memory(operators_data, char_id, char_name, target_elite, target_level):
    """
    内存修改干员练度 (强制模式)
    """
    # 转换为字符串进行对比，防止一个是 int 一个是 string 导致匹配失败
    target_id_str = str(char_id)

    for op in operators_data:
        # 获取当前干员的 ID 和 Name
        current_id_str = str(op.get('id', ''))
        current_name = op.get('name', '')

        # 匹配逻辑：优先匹配 ID，ID 对不上尝试匹配 Name
        match = False
        if current_id_str and current_id_str == target_id_str:
            match = True
        elif current_name and current_name == char_name:
            match = True

        if match:
            # === 强制修改 ===
            # 不再判断 if target > current，只要勾选了就强制设为目标值
            # 这样能保证绝对生效
            op['elite'] = int(target_elite)
            op['level'] = max(int(op.get('level', 0)), int(target_level))  # 等级还是取一下大值比较安全，或者直接设为1

            return True, f"已修改: {current_name} -> 精{op['elite']}"

    return False, f"❌ 未找到干员: {char_name} (ID: {char_id})"


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

    # 初始化分析状态标志位
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False

    # --- 步骤 1: 生成建议 ---
    # 使用 analysis_done 标记来判断，防止空结果导致死循环
    if not st.session_state.analysis_done:
        with st.status("正在分析您的基建潜力...", expanded=True) as status:
            st.write("📥 加载基础数据...")

            temp_ops_path = f"temp_{st.session_state.user_hash}.json"
            temp_conf_path = f"temp_conf_{st.session_state.user_hash}.json"

            try:
                # 写入临时文件
                with open(temp_ops_path, "w", encoding='utf-8') as f:
                    json.dump(st.session_state.user_ops, f)
                with open(temp_conf_path, "w", encoding='utf-8') as f:
                    json.dump(st.session_state.user_conf, f)

                st.write("🧠 运行差异算法...")
                optimizer = WorkplaceOptimizer("efficiency.json", temp_ops_path, temp_conf_path)

                curr = optimizer.get_optimal_assignments(ignore_elite=False)
                pot = optimizer.get_optimal_assignments(ignore_elite=True)

                upgrades = optimizer.calculate_upgrade_requirements(curr, pot)

                # 更新状态
                st.session_state.suggestions = upgrades
                st.session_state.analysis_done = True

                status.update(label="✅ 分析完成！", state="complete", expanded=False)

            except Exception as e:
                status.update(label="❌ 计算出错", state="error")
                st.error(f"算法错误: {str(e)}")
                st.stop()
            finally:
                if os.path.exists(temp_ops_path): os.remove(temp_ops_path)
                if os.path.exists(temp_conf_path): os.remove(temp_conf_path)

            # 强制刷新一次，确保下方 UI 立即更新
            st.rerun()

    else:
        # 分析完成后，显示一个静态的成功提示，避免 UI 突然空了一块
        st.success("✅ 练度分析已完成", icon="📊")

        # --- 步骤 2: 交互式练度确认 ---
        st.markdown("### 1. 练度补全确认")
        st.info("系统检测到您的部分干员提升练度后可大幅增加效率。**勾选并点击生成后，系统将自动记录您的练度提升。**")

        selected_upgrades_indices = []

        if not st.session_state.suggestions:
            st.success("🎉 完美！您当前的练度已达到该布局的理论极限，无需额外提升。")
        else:
            with st.container(border=True):
                st.write("👇 **请勾选您已完成（或计划立即完成）的提升：**")
                cols = st.columns(2)

                for idx, item in enumerate(st.session_state.suggestions):
                    col = cols[idx % 2]

                    # === 修改点：去掉 * 100 ===
                    # 直接使用原始数值，或者根据你的 logic.py 输出决定
                    # 如果 item['gain'] 本来就是 0.05 (5%)，不乘100显示就是 0.05%
                    # 如果 item['gain'] 本来就是 5 (5%)，那就不需要乘
                    # 按照你刚才的要求，这里不再乘 100，直接显示 item['gain']
                    gain_val = item['gain']

                    if item.get('type') == 'bundle':
                        op_names = "+".join([o['name'] for o in item['ops']])
                        # 使用 :.2f 控制小数位数，你可以根据实际数据调整
                        label = f"【组合】{op_names} (效率 +{gain_val:.2f}%)"
                        help_txt = "\n".join([f"{o['name']}: 精{o['current']} -> 精{o['target']}" for o in item['ops']])
                    else:
                        label = f"【单人】{item['name']} (效率 +{gain_val:.2f}%)"
                        help_txt = f"当前: 精{item['current']} -> 目标: 精{item['target']}"

                    s_key = f"suggest_{idx}"
                    if col.checkbox(label, key=s_key, help=help_txt):
                        selected_upgrades_indices.append(idx)

        # --- 步骤 3: 生成最终排班 & 保存数据 ---
        st.markdown("### 2. 获取排班表")

        action_col, _ = st.columns([1, 2])

        if action_col.button("🚀 保存练度并生成排班", type="primary", use_container_width=True):

            # 即使没勾选也允许运行，方便用户生成当前练度的表
            if not selected_upgrades_indices:
                st.info("ℹ️ 未勾选任何提升，将按当前练度生成。")

            with st.spinner("正在写入数据并重新演算..."):

                # === A. 核心数据修改 ===

                # 1. 复制一份当前的原始数据
                # 这里的 user_ops 是从 operators.json 读出来的原始列表
                new_ops_data = copy.deepcopy(st.session_state.user_ops)
                modified_log = []

                # 2. 遍历勾选，强制应用修改
                for idx in selected_upgrades_indices:
                    item = st.session_state.suggestions[idx]

                    if item.get('type') == 'bundle':
                        for o in item['ops']:
                            success, msg = upgrade_operator_in_memory(
                                new_ops_data, o.get('id'), o.get('name'), o['target'], 1
                            )
                            if success: modified_log.append(msg)
                    else:
                        success, msg = upgrade_operator_in_memory(
                            new_ops_data, item.get('id'), item.get('name'), item['target'], 1
                        )
                        if success: modified_log.append(msg)

                # 3. 调试反馈 (如果修改失败，这里能看出来)
                if len(modified_log) > 0:
                    # 打印前3条日志给用户看，确信已修改
                    log_preview = "; ".join(modified_log[:3])
                    if len(modified_log) > 3: log_preview += "..."
                    st.toast(f"✅ 已更新数据: {log_preview}", icon="💾")

                    # === 关键步骤：保存到硬盘 ===
                    try:
                        save_user_data(st.session_state.user_hash, new_ops_data)

                        # === 关键步骤：更新 Session State ===
                        # 确保当前内存里的数据也是新的
                        st.session_state.user_ops = new_ops_data

                        # === 关键步骤：清除缓存 ===
                        # 既然练度变了，旧的建议就无效了。
                        # 清空 analysis_done 标志位。
                        # 这样用户如果刷新页面，系统会重新分析，已完成的建议自然就会消失。
                        st.session_state.analysis_done = False
                        st.session_state.suggestions = []

                    except Exception as e:
                        st.error(f"FATAL: 保存数据失败 - {e}")
                        st.stop()
                elif selected_upgrades_indices:
                    # 勾选了但没日志，说明匹配全失败了
                    st.error("⚠️ 错误：无法匹配干员ID。请检查 operators.json 数据格式。")
                    st.write("Debug - Target IDs:",
                             [st.session_state.suggestions[i]['name'] for i in selected_upgrades_indices])

                # === B. 计算排班 (使用修改后的 new_ops_data) ===

                run_ops_path = f"run_ops_{st.session_state.user_hash}.json"
                run_conf_path = f"run_conf_{st.session_state.user_hash}.json"

                # 写入临时文件供算法读取
                with open(run_ops_path, "w", encoding='utf-8') as f:
                    json.dump(new_ops_data, f, ensure_ascii=False)
                with open(run_conf_path, "w", encoding='utf-8') as f:
                    json.dump(st.session_state.user_conf, f, ensure_ascii=False)

                try:
                    # 调用算法
                    # ignore_elite=False -> 必须为 False，因为我们要基于 new_ops_data (其中已包含了我们刚才强制修改的精二数据) 来计算
                    optimizer = WorkplaceOptimizer("efficiency.json", run_ops_path, run_conf_path)
                    final_result = optimizer.get_optimal_assignments(ignore_elite=False)

                    # 提取效率
                    raw_res = final_result.get('raw_results', [])
                    current_efficiency = raw_res[0].total_efficiency if raw_res else 0
                    st.session_state.final_eff = current_efficiency

                    # 清洗结果 (去除不可序列化对象)
                    cleaned_result = clean_data(final_result)
                    st.session_state.final_result_json = json.dumps(cleaned_result, ensure_ascii=False, indent=2)

                    st.balloons()

                except Exception as e:
                    st.error(f"计算过程发生错误: {str(e)}")
                finally:
                    # 清理临时文件
                    if os.path.exists(run_ops_path): os.remove(run_ops_path)
                    if os.path.exists(run_conf_path): os.remove(run_conf_path)

        # 结果展示区
        if 'final_result_json' in st.session_state:
            st.markdown("---")
            r_col1, r_col2 = st.columns([1, 1])

            with r_col1:
                # 这里去掉了 delta，因为没有比较基准了
                st.metric("预计最终效率", f"{st.session_state.final_eff:.2f}")  # 如果本来就是百分比数值，这里不带%符号，看你需求

                st.download_button(
                    label="📥 下载 MAA 排班文件 (JSON)",
                    data=st.session_state.final_result_json,
                    file_name="maa_schedule_optimized.json",
                    mime="application/json",
                    use_container_width=True
                )

            with r_col2:
                st.info("""
                    **操作成功！**
                    1. 上方文件已包含您勾选的练度提升。
                    2. **请按 F5 刷新页面**：您会发现刚才勾选的建议已经消失（因为系统已记录您完成了这些提升）。
                    """)