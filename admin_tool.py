# admin_tool.py
import hashlib
import os
import json
import shutil


def generate_hash(order_id):
    # 使用 SHA256 并截取前 16 位作为目录名，既安全又不过长
    return hashlib.sha256(order_id.strip().encode('utf-8')).hexdigest()[:16]


def setup_user(order_id, ops_source_path, config_type):
    """
    order_id: 闲鱼订单号
    ops_source_path: 客户发给你的 operators.json 路径
    config_type: 配置类型 (如 '243_balanced', '333_max_lmd')
    """
    user_hash = generate_hash(order_id)
    target_dir = os.path.join("user_data", user_hash)

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    # 1. 复制/写入 operators.json
    try:
        shutil.copy(ops_source_path, os.path.join(target_dir, "operators.json"))
    except FileNotFoundError:
        print(f"❌ 找不到源文件: {ops_source_path}")
        return

    # 2. 生成 config.json (根据你的业务逻辑预设好模板)
    # 这里你可以扩展更多的 config 模板
    config_templates = {
        "243": {
            "layout": "2-4-3",
            "desc": "243 均衡流 (2赤金/2经验)",
            "product_requirements": {"trading_stations": {"LMD": 2}, "manufacturing_stations": {"Pure Gold": 2, "Battle Record": 2}}
        },
        "333": {
            "layout": "3-3-3",
            "desc": "333 搓玉流",
            "product_requirements": {"trading_stations": {"LMD": 3}, "manufacturing_stations": {"Pure Gold": 2, "Battle Record": 1}}
        }
    }

    selected_config = config_templates.get(config_type, config_templates["243"])

    with open(os.path.join(target_dir, "config.json"), "w", encoding='utf-8') as f:
        json.dump(selected_config, f, indent=2, ensure_ascii=False)

    print(f"✅ 用户设置完成!")
    print(f"订单号: {order_id}")
    print(f"Hash Key: {user_hash}")
    print(f"数据路径: {target_dir}")


# --- 使用示例 ---
if __name__ == "__main__":
    print("=== MAA 售后数据生成器 ===")
    oid = input("输入闲鱼订单号: ")
    path = input("operators.json 路径 (直接拖入): ").strip('"')
    c_type = input("配置类型 (243 / 333): ")
    setup_user(oid, path, c_type)