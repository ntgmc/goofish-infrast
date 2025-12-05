import datetime
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


# ----------------- 数据类定义 -----------------

@dataclass
class Operator:
    id: str
    name: str
    elite: int
    level: int
    own: bool
    potential: int
    rarity: int


@dataclass
class RoomRequirement:
    operator: str
    elite_required: int


@dataclass
class OperatorEfficiency:
    operators: List[str]
    workplace_type: str
    base_efficiency: float
    synergy_efficiency: float
    description: str
    elite_requirements: Dict[str, int]
    requires_control_center: List[RoomRequirement]
    requires_dormitory: List[RoomRequirement]
    requires_power_station: List[RoomRequirement]
    requires_hire: List[RoomRequirement]
    requires_processing_station: List[RoomRequirement]  # [新增] 加工站需求
    special_conditions: Optional[str] = None
    apply_each: bool = False
    priority: int = 0
    products: List[str] = field(default_factory=list)


@dataclass
class Workplace:
    id: str
    name: str
    max_operators: int
    base_efficiency: float
    products: List[str] = field(default_factory=list)
    current_product: str = ""


@dataclass
class AssignmentResult:
    workplace: Workplace
    optimal_operators: List[Operator]
    total_efficiency: float
    operator_efficiency: float
    applied_combinations: List[str]
    applied_rules: List[OperatorEfficiency]
    control_center_requirements: List[RoomRequirement]
    dormitory_requirements: List[RoomRequirement]
    power_station_requirements: List[RoomRequirement]
    hire_requirements: List[RoomRequirement]
    processing_station_requirements: List[RoomRequirement]  # [新增] 加工站需求结果
    assignment_detail: List[Dict] = field(default_factory=list)  # [新增] 详细分配信息


@dataclass
class ControlCenterRule:
    operators: List[str]
    description: str
    efficiency: float
    priority: int
    group: Optional[str] = None
    elite_requirements: Dict[str, int] = field(default_factory=dict)


# ----------------- 优化器类定义 -----------------

class WorkplaceOptimizer:
    def __init__(self, efficiency_file: str, operator_file: str, config_file: str = None, debug: bool = False):
        self.efficiency_file = efficiency_file
        self.operator_file = operator_file
        self.config_file = config_file
        self.debug = debug

        self.efficiency_data = self.load_json(efficiency_file)
        self.operator_data = self.load_json(operator_file)
        self.config_data = self.load_json(config_file) if config_file else {}

        self.trading_stations_count = self.config_data.get('trading_stations_count', 3)
        self.manufacturing_stations_count = self.config_data.get('manufacturing_stations_count', 3)

        self.operators = self.load_operators()
        self.efficiency_rules = self.load_efficiency_rules()
        self.cc_rules = self.load_cc_rules()

        # 动态调整清流效率
        for rule in self.efficiency_rules:
            if rule.workplace_type == 'manufacturing_station' and rule.operators == ['清流']:
                rule.synergy_efficiency = self.trading_stations_count * 20
                break

        self.workplaces = self.load_workplaces()
        self.fiammetta_targets = []

    def load_json(self, file_path: str) -> Any:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: File {file_path} not found.")
            return {}

    def load_operators(self) -> Dict[str, Operator]:
        operators = {}
        for op_data in self.operator_data:
            operators[op_data['name']] = Operator(
                id=op_data['id'],
                name=op_data['name'],
                elite=op_data['elite'],
                level=op_data['level'],
                own=op_data['own'],
                potential=op_data['potential'],
                rarity=op_data['rarity']
            )
        return operators

    def load_efficiency_rules(self) -> List[OperatorEfficiency]:
        expanded_rules: List[OperatorEfficiency] = []

        def parse_operator_string(op_str: str) -> tuple[str, int]:
            if '/' in op_str:
                name, elite_str = op_str.split('/', 1)
                return name.strip(), int(elite_str.strip())
            else:
                return op_str.strip(), 0

        expanded_rules = []
        for workplace_type, systems in self.efficiency_data.get('combination_rules', {}).items():
            for system_name, system_data in systems.items():
                if isinstance(system_data, list):
                    for rule_data in system_data:
                        operators = []
                        elite_requirements = {}
                        for op_str in rule_data['combo']:
                            name, elite = parse_operator_string(op_str)
                            operators.append(name)
                            if elite > 0: elite_requirements[name] = elite

                        # 辅助函数：解析房间需求
                        def parse_reqs(key):
                            reqs = []
                            if key in rule_data:
                                for s in rule_data[key]:
                                    n, e = parse_operator_string(s)
                                    reqs.append(RoomRequirement(operator=n, elite_required=e))
                            return reqs

                        products = rule_data.get('product', [])
                        if isinstance(products, str): products = [products]

                        expanded_rules.append(OperatorEfficiency(
                            operators=operators,
                            workplace_type=workplace_type,
                            base_efficiency=0,
                            synergy_efficiency=rule_data['efficiency'],
                            description=f"{system_name}" if rule_data.get(
                                'apply_each') else f"{system_name} - {', '.join(operators)}",
                            elite_requirements=elite_requirements,
                            requires_control_center=parse_reqs('control_center'),
                            requires_dormitory=parse_reqs('dormitory'),
                            requires_power_station=parse_reqs('power_station'),
                            requires_hire=parse_reqs('hire'),
                            requires_processing_station=parse_reqs('process'),
                            apply_each=rule_data.get('apply_each', False),
                            priority=rule_data.get('priority', 0),
                            products=products
                        ))
                elif isinstance(system_data, dict):
                    # 处理复杂体系
                    base_operators = []
                    base_elite_requirements = {}
                    base_products = system_data.get('product', [])
                    if isinstance(base_products, str): base_products = [base_products]

                    if 'base_combo' in system_data:
                        for op_str in system_data['base_combo']:
                            name, elite = parse_operator_string(op_str)
                            base_operators.append(name)
                            if elite > 0: base_elite_requirements[name] = elite

                    for rule_data in system_data.get('rules', []):
                        all_ops = base_operators.copy()
                        all_elites = base_elite_requirements.copy()
                        for op_str in rule_data.get('combo', []):
                            name, elite = parse_operator_string(op_str)
                            all_ops.append(name)
                            if elite > 0: all_elites[name] = elite

                        def parse_reqs_rule(key):
                            reqs = []
                            if key in rule_data:
                                for s in rule_data[key]:
                                    n, e = parse_operator_string(s)
                                    reqs.append(RoomRequirement(operator=n, elite_required=e))
                            return reqs

                        p = rule_data.get('product', base_products)
                        if isinstance(p, str):
                            p = [p]
                        elif not isinstance(p, list):
                            p = base_products

                        expanded_rules.append(OperatorEfficiency(
                            operators=all_ops,
                            workplace_type=workplace_type,
                            base_efficiency=0,
                            synergy_efficiency=rule_data['efficiency'],
                            description=f"{system_name} - {', '.join(all_ops)}",
                            elite_requirements=all_elites,
                            requires_control_center=parse_reqs_rule('control_center'),
                            requires_dormitory=parse_reqs_rule('dormitory'),
                            requires_power_station=parse_reqs_rule('power_station'),
                            requires_hire=parse_reqs_rule('hire'),
                            requires_processing_station=parse_reqs_rule('process'),
                            apply_each=rule_data.get('apply_each', False),
                            priority=rule_data.get('priority', 0),
                            products=p
                        ))

        expanded_rules.sort(key=lambda r: (r.priority, r.synergy_efficiency), reverse=True)
        return expanded_rules

    def load_cc_rules(self) -> List[ControlCenterRule]:
        rules = []
        raw_rules = self.efficiency_data.get('control_center_rules', [])

        for r in raw_rules:
            # 1. 获取干员列表，兼容 'operators' 和 'operator' 两种写法
            raw_ops = r.get('operators', r.get('operator', []))
            if isinstance(raw_ops, str):
                raw_ops = [raw_ops]

            # 2. 检查是否是 apply_each (逐个应用) 模式
            is_apply_each = r.get('apply_each', False)

            description = r.get('description', "")
            efficiency = r.get('efficiency', 0)
            priority = r.get('priority', 0)
            group = r.get('group', None)

            # 辅助函数：解析 "干员名/精英等级"
            def parse_single_op(op_str):
                if '/' in op_str:
                    name, elite = op_str.split('/')
                    return name, int(elite)
                return op_str, 0

            if is_apply_each:
                # === 模式 A: 拆分成多条单人规则 ===
                for op_str in raw_ops:
                    name, elite_req = parse_single_op(op_str)

                    # 为每个人创建一条独立的规则
                    rules.append(ControlCenterRule(
                        operators=[name],  # 列表里只有一个人
                        description=description,  # 描述共用
                        efficiency=efficiency,
                        priority=priority,
                        group=group,
                        elite_requirements={name: elite_req} if elite_req > 0 else {}
                    ))
            else:
                # === 模式 B: 组合规则 (原有逻辑) ===
                # 必须所有人同时在场才生效
                ops_list = []
                elites_dict = {}
                for op_str in raw_ops:
                    name, elite_req = parse_single_op(op_str)
                    ops_list.append(name)
                    if elite_req > 0:
                        elites_dict[name] = elite_req

                rules.append(ControlCenterRule(
                    operators=ops_list,
                    description=description,
                    efficiency=efficiency,
                    priority=priority,
                    group=group,
                    elite_requirements=elites_dict
                ))

        # 排序：优先处理优先级高(priority)的，其次效率高(efficiency)的
        # 你的心情干员 efficiency 只有 0.05，自然会排在贸易站加成(0.07)之后，作为填充物
        rules.sort(key=lambda x: (x.priority, x.efficiency), reverse=True)
        return rules

    def load_workplaces(self) -> Dict[str, List[Workplace]]:
        # 保持原有的 load_workplaces 逻辑
        workplaces = {
            'trading_stations': [], 'manufacturing_stations': [],
            'meeting_room': [], 'power_station': []
        }
        default_trading = self.efficiency_data['workplaces']['trading_stations'][0] if \
            self.efficiency_data['workplaces']['trading_stations'] else {'max_operators': 3, 'base_efficiency': 100}
        default_manufacturing = self.efficiency_data['workplaces']['manufacturing_stations'][0] if \
            self.efficiency_data['workplaces']['manufacturing_stations'] else {'max_operators': 3,
                                                                               'base_efficiency': 100}

        for i in range(self.trading_stations_count):
            workplaces['trading_stations'].append(
                Workplace(id=f"trading_{i + 1}", name=f"贸易站{i + 1}", max_operators=default_trading['max_operators'],
                          base_efficiency=default_trading['base_efficiency']))
        for i in range(self.manufacturing_stations_count):
            workplaces['manufacturing_stations'].append(Workplace(id=f"manufacturing_{i + 1}", name=f"制造站{i + 1}",
                                                                  max_operators=default_manufacturing['max_operators'],
                                                                  base_efficiency=default_manufacturing[
                                                                      'base_efficiency']))

        if self.efficiency_data['workplaces']['meeting_room']:
            m_data = self.efficiency_data['workplaces']['meeting_room']
            workplaces['meeting_room'].append(
                Workplace(id=m_data['id'], name=m_data['name'], max_operators=m_data['max_operators'],
                          base_efficiency=m_data['base_efficiency']))

        for ps_data in self.efficiency_data['workplaces']['power_station']:
            workplaces['power_station'].append(
                Workplace(id=ps_data['id'], name=ps_data['name'], max_operators=ps_data['max_operators'],
                          base_efficiency=ps_data['base_efficiency']))

        return workplaces

    def get_available_operators(self) -> List[Operator]:
        return [op for op in self.operators.values() if op.own]

    # --------------- 核心修改：增加 ignore_elite 参数 ---------------

    def check_elite_requirements(self, operators: List[Operator], elite_requirements: Dict[str, int],
                                 ignore_elite: bool = False) -> bool:
        """检查干员是否满足精英化要求。如果 ignore_elite 为 True，则只检查干员是否拥有（已在上层过滤），忽略等级。"""
        if ignore_elite:
            return True

        operator_dict = {op.name: op for op in operators}
        for op_name, required_elite in elite_requirements.items():
            if op_name in operator_dict:
                if operator_dict[op_name].elite < required_elite:
                    return False
        return True

    def check_room_requirements(self, room_reqs: List[RoomRequirement],
                                operator_usage: Dict[str, int],  # 新增参数
                                ignore_elite: bool = False) -> bool:
        """检查房间需求，增加 operator_usage 参数"""
        for req in room_reqs:
            if req.operator not in self.operators:
                return False
            op = self.operators[req.operator]
            if not op.own:
                return False
            if not ignore_elite and op.elite < req.elite_required:
                return False

            # [新增] 检查该附属干员是否已经上了2个班
            # 注意：这里我们不做 shift_used_names 检查，因为那是当前班次的冲突，
            # 而这里主要检查是否疲劳。当前班次冲突由外部逻辑保证。
            if operator_usage.get(req.operator, 0) >= 2:
                return False

        return True

    def check_fiammetta_available(self, ignore_elite: bool = False) -> bool:
        """检查菲亚梅塔是否可用"""
        if '菲亚梅塔' not in self.operators:
            return False
        op = self.operators['菲亚梅塔']
        if not op.own:
            return False
        # 如果忽略等级限制，只要拥有即可；否则需要精二
        return True if ignore_elite else op.elite >= 2

    def get_workplace_type(self, workplace: Workplace) -> str:
        if 'trading' in workplace.id:
            return 'trading_station'
        elif 'manufacturing' in workplace.id:
            return 'manufacturing_station'
        elif 'meeting' in workplace.id:
            return 'meeting_room'
        elif 'power' in workplace.id:
            return 'power_station'
        else:
            return workplace.id.split('_')[0] + '_station'

    def calculate_dynamic_efficiency(self, rule, op_objs, workplace_type, ignore_elite=False):
        """计算动态效率，包含会客室的特殊加成"""
        base_eff = rule.synergy_efficiency
        if workplace_type == 'meeting_room':
            bonus = 0
            for op in op_objs:
                # 基础加成 5%
                bonus += 5

                # 确定计算用的精英化等级
                calc_elite = op.elite

                # 如果是潜在方案计算 (ignore_elite=True)，且当前等级不满足需求，
                # 我们应该使用规则要求的等级来计算潜在收益
                if ignore_elite:
                    req_elite = rule.elite_requirements.get(op.name, 0)
                    # 如果当前等级低于要求，使用要求的等级计算
                    if op.elite < req_elite:
                        calc_elite = req_elite

                # 精英化加成
                if calc_elite == 2:
                    bonus += 16
                elif calc_elite == 1:
                    bonus += 8
            return base_eff + bonus
        return base_eff

    def optimize_workplace(self, workplace: Workplace, operator_usage: Dict[str, int],
                           shift_used_names: set, ignore_elite: bool = False) -> AssignmentResult:
        """优化单个工作站的干员配置，增加 ignore_elite 参数"""
        available_ops = self.get_available_operators()
        op_by_name = {op.name: op for op in available_ops}
        workplace_type = self.get_workplace_type(workplace)

        def rule_matches_products(rule: OperatorEfficiency) -> bool:
            if not rule.products: return True
            return workplace.current_product in rule.products

        remaining_slots = workplace.max_operators
        assigned_ops: List[Operator] = []
        used_names = set()
        total_synergy = 0.0
        applied_combinations: List[str] = []
        applied_rules: List[OperatorEfficiency] = []  # 新增

        # 收集需求
        applied_reqs = {
            'control': [], 'dorm': [], 'power': [], 'hire': [], 'process': []
        }

        all_rules = [r for r in self.efficiency_rules if
                     r.workplace_type == workplace_type and rule_matches_products(r)]

        system_groups = {}
        for rule in all_rules:
            sys_name = "通用"
            for sys_key in self.efficiency_data['combination_rules'].get(workplace_type, {}):
                if sys_key in rule.description:
                    sys_name = sys_key
                    break
            if sys_name not in system_groups: system_groups[sys_name] = []
            system_groups[sys_name].append(rule)

        for name, rules in system_groups.items():
            rules.sort(key=lambda r: (r.priority, r.synergy_efficiency), reverse=True)

        # 评估逻辑
        best_candidate = None
        best_efficiency = -1

        # ----------------- 辅助函数：判断是否是“孤立”的自动化干员 -----------------
        def calculate_adjusted_efficiency(rule, required_ops, current_slots, rule_efficiency=None):
            """
            计算修正后的效率。
            针对自动化体系：如果清流不可用，且当前规则不能填满房间，
            则该规则的效率应该分摊到剩余所有空位上（因为余下的空位将无法放置通用干员）。
            """
            base_total_eff = rule_efficiency if rule_efficiency is not None else rule.synergy_efficiency
            base_eff = base_total_eff / len(required_ops)

            # 判断是否是自动化体系
            is_automation = "自动化" in rule.description

            # 检查清流是否可用（不在当前规则中，但库存里有）
            purestream_available = False
            if '清流' in op_by_name and '清流' not in shift_used_names and '清流' not in used_names:
                if operator_usage.get('清流', 0) < 2:  # 假设清流没满班
                    purestream_available = True

            # 如果规则本身包含清流，那自然是可用的
            if '清流' in required_ops:
                purestream_available = True

            if is_automation and workplace_type == 'manufacturing_station':
                # 如果这个规则填不满剩余位置
                if len(required_ops) < current_slots:
                    # 且没有清流来救场
                    if not purestream_available:
                        # 那么剩余的空位实际上是废的。效率必须分摊到所有剩余位置上。
                        return base_total_eff / current_slots

            return base_eff

            # ----------------- 1. 评估体系 -----------------
            for system_name, rules in system_groups.items():
                if system_name == "通用": continue
                for rule in rules:
                    if remaining_slots <= 0: break

                    required = rule.operators

                    # 1. 检查干员是否可用、是否占用、是否满班
                    unavailable_ops = []
                    for op_name in required:
                        max_usage = 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                        if (
                                op_name not in op_by_name or
                                op_name in used_names or
                                op_name in shift_used_names or
                                operator_usage.get(op_name, 0) >= max_usage
                        ):
                            unavailable_ops.append(op_name)

                    if unavailable_ops or len(required) > remaining_slots:
                        continue

                    # =========================================================================
                    # === [修改开始] 特殊依赖检查：制造站迷迭香体系的前置检查 ===
                    # =========================================================================
                    # 只有当规则是制造站的迷迭香，且效率极高（>200，代表满配体系）时触发
                    if workplace_type == 'manufacturing_station' and "迷迭香" in required and rule.synergy_efficiency > 200:
                        # 必须保证 黑键 和 乌有 在接下来的贸易站计算中是“可用”的
                        # 如果他们不可用，这个迷迭香的高效规则就不能成立
                        partners_check = [("黑键", 2), ("乌有", 2)]
                        partners_ok = True

                        for p_name, p_elite in partners_check:
                            # A. 检查是否有这个干员
                            if p_name not in op_by_name:
                                partners_ok = False;
                                break

                            # B. 检查是否已经被本班次其他房间（比如还没轮到的贸易站? 不可能，因为制造站先算）
                            # 这里主要是防止他们被错误地排进了当前制造站的其他位置（虽然不太可能）
                            # 或者在未来的逻辑修改中顺序变动
                            if p_name in shift_used_names or p_name in used_names:
                                partners_ok = False;
                                break

                            # C. 检查疲劳度 (是否还能上班)
                            # 黑键/乌有通常是2班倒，除非被菲亚梅塔选中
                            p_max_usage = 3 if p_name in self.fiammetta_targets else 2
                            if operator_usage.get(p_name, 0) >= p_max_usage:
                                partners_ok = False;
                                break

                            # D. 检查练度 (如果不忽略练度)
                            if not ignore_elite:
                                p_op = op_by_name[p_name]
                                if p_op.elite < p_elite:
                                    partners_ok = False;
                                    break

                        if not partners_ok:
                            continue  # 如果黑键或乌有不可用，跳过这条迷迭香的规则，去匹配低效率的通用规则
                    # =========================================================================
                    # === [修改结束] ===
                    # =========================================================================

                # 2. 特殊依赖检查：黑键/乌有 需要 迷迭香
                if workplace_type == 'trading_station' and ('黑键' in required or '乌有' in required):
                    # 检查当前班次是否已经使用了 迷迭香
                    if '迷迭香' not in shift_used_names:
                        continue

                        # 3. 现在可以安全地生成对象列表了（因为已经确认所有人都有了）
                op_objs = [op_by_name[op_name] for op_name in required]

                # 4. 检查精英化等级
                if not ignore_elite:
                    if "孑0体系" in rule.description:
                        if not any(op.name == "孑" and op.elite == 0 for op in op_objs if op.name == "孑"): continue
                    elif "孑12体系" in rule.description:
                        if not any(
                                op.name == "孑" and op.elite in [1, 2] for op in op_objs if op.name == "孑"): continue

                if not self.check_elite_requirements(op_objs, rule.elite_requirements, ignore_elite): continue

                # 5. 检查房间需求
                if not self.check_room_requirements(rule.requires_control_center, operator_usage,
                                                    ignore_elite): continue
                if not self.check_room_requirements(rule.requires_dormitory, operator_usage, ignore_elite): continue
                if not self.check_room_requirements(rule.requires_power_station, operator_usage, ignore_elite): continue
                if not self.check_room_requirements(rule.requires_hire, operator_usage, ignore_elite): continue

                # [新增] 检查加工站需求
                if hasattr(rule, 'requires_processing_station') and rule.requires_processing_station:
                    if not self.check_room_requirements(rule.requires_processing_station, operator_usage,
                                                        ignore_elite): continue

                # === 计算效率 ===
                real_eff = self.calculate_dynamic_efficiency(rule, op_objs, workplace_type, ignore_elite)
                efficiency_per_slot = calculate_adjusted_efficiency(rule, required, remaining_slots, real_eff)

                if efficiency_per_slot > best_efficiency:
                    best_efficiency = efficiency_per_slot
                    best_candidate = {'type': 'system', 'rule': rule, 'required': required,
                                      'efficiency': real_eff, 'slots_used': len(required)}

        # ----------------- 2. 评估通用 -----------------
        generic_rules = system_groups.get("通用", [])
        for rule in generic_rules:
            # ... (这部分的逻辑通常不需要改，因为通用干员不排斥其他人) ...
            # 但为了保持代码一致性，我们看下是否有影响。通常不需要动。
            # 直接看 else 分支 (非 apply_each 的通用组合)
            if remaining_slots <= 0: break

            if rule.apply_each:
                for op_name in rule.operators:
                    max_usage = 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                    if (
                            remaining_slots <= 0 or op_name in used_names or op_name in shift_used_names or op_name not in op_by_name or operator_usage.get(
                        op_name, 0) >= max_usage): continue

                    op_obj = op_by_name[op_name]
                    req_elite = {op_name: rule.elite_requirements.get(op_name, 0)}

                    if not self.check_elite_requirements([op_obj], req_elite, ignore_elite): continue
                    if (not self.check_room_requirements(rule.requires_control_center, operator_usage, ignore_elite) or
                            not self.check_room_requirements(rule.requires_dormitory, operator_usage,
                                                             ignore_elite)): continue

                    real_eff = self.calculate_dynamic_efficiency(rule, [op_obj], workplace_type, ignore_elite)
                    eff = real_eff
                    if eff > best_efficiency:
                        best_efficiency = eff
                        best_candidate = {'type': 'generic_each', 'rule': rule, 'required': [op_name],
                                          'efficiency': eff, 'slots_used': 1}
            else:
                required = rule.operators
                max_check = lambda n: 3 if n in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                if any(n not in op_by_name or n in used_names or n in shift_used_names or operator_usage.get(n,
                                                                                                             0) >= max_check(
                    n) for n in required) or len(required) > remaining_slots:
                    continue

                op_objs = [op_by_name[n] for n in required]
                if (not self.check_elite_requirements(op_objs, rule.elite_requirements, ignore_elite) or
                        not self.check_room_requirements(rule.requires_control_center, operator_usage, ignore_elite) or
                        not self.check_room_requirements(rule.requires_dormitory, operator_usage, ignore_elite) or
                        not self.check_room_requirements(rule.requires_power_station, operator_usage, ignore_elite) or
                        not self.check_room_requirements(rule.requires_hire, operator_usage, ignore_elite)):
                    continue

                # === 修改点：通用组也用一下这个函数比较保险，虽然通常没影响 ===
                real_eff = self.calculate_dynamic_efficiency(rule, op_objs, workplace_type, ignore_elite)
                efficiency_per_slot = calculate_adjusted_efficiency(rule, required, remaining_slots, real_eff)

                if efficiency_per_slot > best_efficiency:
                    best_efficiency = efficiency_per_slot
                    best_candidate = {'type': 'generic', 'rule': rule, 'required': required,
                                      'efficiency': real_eff, 'slots_used': len(required)}

        if best_candidate and best_efficiency > 0:
            rule = best_candidate['rule']
            required = best_candidate['required']
            for op_name in required:
                assigned_ops.append(op_by_name[op_name])
                used_names.add(op_name)
                shift_used_names.add(op_name)
                operator_usage[op_name] += 1
            remaining_slots -= best_candidate['slots_used']
            total_synergy += best_candidate['efficiency']

            applied_rules.append(rule)  # 记录规则

            desc = f"{rule.description}({', '.join(required)})" if best_candidate[
                                                                       'type'] == 'generic_each' else rule.description
            applied_combinations.append(desc)

            applied_reqs['control'].extend(rule.requires_control_center)
            applied_reqs['dorm'].extend(rule.requires_dormitory)
            applied_reqs['power'].extend(rule.requires_power_station)
            applied_reqs['hire'].extend(rule.requires_hire)
            applied_reqs['process'].extend(rule.requires_processing_station)

            # [新增] 记录详细分配信息，用于练度计算归因
            assignment_detail = [
                {'rule': rule, 'ops': required, 'eff': best_candidate['efficiency'], 'type': best_candidate['type']}]
        else:
            assignment_detail = []

        if remaining_slots > 0:
            rec_res = self.optimize_workplace_recursive(
                workplace, operator_usage, shift_used_names, assigned_ops, used_names, remaining_slots,
                applied_combinations, ignore_elite, applied_rules
            )
            assigned_ops.extend(rec_res['assigned_ops'])
            total_synergy += rec_res['total_synergy']
            applied_combinations.extend(rec_res['applied_combinations'])
            applied_rules.extend(rec_res['applied_rules'])  # 记录规则
            applied_reqs['control'].extend(rec_res['reqs']['control'])
            applied_reqs['dorm'].extend(rec_res['reqs']['dorm'])
            applied_reqs['power'].extend(rec_res['reqs']['power'])
            applied_reqs['hire'].extend(rec_res['reqs']['hire'])
            assignment_detail.extend(rec_res['assignment_detail'])

        return AssignmentResult(
            workplace=workplace,
            optimal_operators=assigned_ops,
            total_efficiency=workplace.base_efficiency + total_synergy,
            operator_efficiency=total_synergy,
            applied_combinations=applied_combinations,
            applied_rules=applied_rules,
            control_center_requirements=applied_reqs['control'],
            dormitory_requirements=applied_reqs['dorm'],
            power_station_requirements=applied_reqs['power'],
            hire_requirements=applied_reqs['hire'],
            processing_station_requirements=applied_reqs['process'],
            assignment_detail=assignment_detail  # [新增]
        )

    def optimize_workplace_recursive(self, workplace, operator_usage, shift_used_names, assigned_ops, used_names,
                                     remaining_slots, applied_combinations, ignore_elite, applied_rules_list):
        available_ops = self.get_available_operators()
        op_by_name = {op.name: op for op in available_ops}
        workplace_type = self.get_workplace_type(workplace)

        local_synergy = 0
        local_combos = []
        local_rules = []
        local_details = []  # [新增]
        local_reqs = {'control': [], 'dorm': [], 'power': [], 'hire': []}

        # 1. 分析当前房间的属性（是自动化房，还是通用房？）
        room_has_automation = False
        room_has_generic = False

        for r in applied_rules_list:
            # 判断规则是否属于自动化体系
            is_auto = "自动化" in r.description
            # 判断规则是否包含清流（清流是中立的，既兼容自动化也兼容通用）
            is_pure = "清流" in r.operators

            if is_auto:
                room_has_automation = True
            elif not is_pure:
                # 如果既不是自动化规则，又不包含清流，那就是通用规则
                room_has_generic = True

        # 如果逻辑正常，room_has_automation 和 room_has_generic 不应同时为 True
        # 但如果发生了，优先视作自动化房（因为通用效率已被清空）

        def rule_matches_products(rule):
            if not rule.products: return True
            return workplace.current_product in rule.products

        while remaining_slots > 0:
            best_cand = None
            best_eff = -1

            all_rules = [r for r in self.efficiency_rules if
                         r.workplace_type == workplace_type and rule_matches_products(r)]

            for rule in all_rules:
                # --- 严格的互斥逻辑 (Gate Keeper) ---

                rule_is_auto = "自动化" in rule.description
                rule_has_pure = "清流" in rule.operators
                rule_is_generic = not rule_is_auto and not rule_has_pure

                # 门禁 1: 如果房间已经是自动化房，严禁放入通用干员
                if room_has_automation:
                    if rule_is_generic:
                        continue  # 跳过通用干员

                # 门禁 2: 如果房间已经是通用房，严禁放入自动化干员
                if room_has_generic:
                    if rule_is_auto:
                        continue  # 跳过自动化干员

                # -----------------------------------

                if rule.apply_each:
                    for op_name in rule.operators:
                        max_usage = 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                        if (
                                op_name in used_names or op_name in shift_used_names or op_name not in op_by_name or operator_usage.get(
                            op_name, 0) >= max_usage): continue

                        op_obj = op_by_name[op_name]
                        req_elite = {op_name: rule.elite_requirements.get(op_name, 0)}
                        if (not self.check_elite_requirements([op_obj], req_elite, ignore_elite) or
                                not self.check_room_requirements(rule.requires_control_center, operator_usage,
                                                                 ignore_elite) or
                                not self.check_room_requirements(rule.requires_dormitory, operator_usage,
                                                                 ignore_elite) or
                                not self.check_room_requirements(rule.requires_power_station, operator_usage,
                                                                 ignore_elite) or
                                not self.check_room_requirements(rule.requires_hire, operator_usage,
                                                                 ignore_elite)): continue

                        real_eff = self.calculate_dynamic_efficiency(rule, [op_obj], workplace_type)
                        if real_eff > best_eff:
                            best_eff = real_eff
                            best_cand = {'rule': rule, 'req': [op_name], 'eff': best_eff, 'slots': 1, 'type': 'each'}
                else:
                    req = rule.operators
                    if len(req) > remaining_slots: continue
                    max_check = lambda \
                            n: 3 if n in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                    if any(n in used_names or n in shift_used_names or n not in op_by_name or operator_usage.get(n,
                                                                                                                 0) >= max_check(
                        n) for n in req): continue

                    op_objs = [op_by_name[n] for n in req]
                    if (not self.check_elite_requirements(op_objs, rule.elite_requirements, ignore_elite) or
                            not self.check_room_requirements(rule.requires_control_center, operator_usage,
                                                             ignore_elite) or
                            not self.check_room_requirements(rule.requires_dormitory, operator_usage, ignore_elite) or
                            not self.check_room_requirements(rule.requires_power_station, operator_usage,
                                                             ignore_elite) or
                            not self.check_room_requirements(rule.requires_hire, operator_usage,
                                                             ignore_elite)): continue

                    real_eff = self.calculate_dynamic_efficiency(rule, op_objs, workplace_type)
                    eff_per = real_eff / len(req)
                    if eff_per > best_eff:
                        best_eff = eff_per
                        best_cand = {'rule': rule, 'req': req, 'eff': real_eff, 'slots': len(req),
                                     'type': 'norm'}

            if best_cand:
                rule = best_cand['rule']
                req = best_cand['req']
                for n in req:
                    assigned_ops.append(op_by_name[n])
                    used_names.add(n)
                    shift_used_names.add(n)
                    operator_usage[n] += 1
                remaining_slots -= best_cand['slots']
                local_synergy += best_cand['eff']
                local_rules.append(rule)
                # 更新当前递归层级的房间状态，影响下一次循环
                if "自动化" in rule.description:
                    room_has_automation = True
                elif "清流" not in rule.operators:  # 非自动化且非清流
                    room_has_generic = True

                desc = f"{rule.description}({', '.join(req)})" if best_cand['type'] == 'each' else rule.description
                local_combos.append(desc)

                local_reqs['control'].extend(rule.requires_control_center)
                local_reqs['dorm'].extend(rule.requires_dormitory)
                local_reqs['power'].extend(rule.requires_power_station)
                local_reqs['hire'].extend(rule.requires_hire)

                local_details.append({'rule': rule, 'ops': req, 'eff': best_cand['eff'], 'type': best_cand['type']})
            else:
                break

        return {
            'assigned_ops': [], 'total_synergy': local_synergy, 'applied_combinations': local_combos,
            'applied_rules': local_rules, 'reqs': local_reqs, 'assignment_detail': local_details
        }

    def fill_control_center(self, plan: Dict, shift_used_names: set, operator_usage: Dict, ignore_elite: bool):
        """
        填充控制中枢剩余位置，处理互斥逻辑，并增加班次限制
        """
        current_cc_ops = plan["rooms"]["control"][0]["operators"]
        remaining_slots = 5 - len(current_cc_ops)
        if remaining_slots <= 0:
            return

        # 1. 标记已占用的互斥组 (Group)
        used_groups = set()
        for op_name in current_cc_ops:
            for rule in self.cc_rules:
                if op_name in rule.operators and rule.group:
                    # 简单策略：如果某人已经在里面了，且这个人是某条规则的成员，则尝试锁定组
                    # (为了更严谨，这里假设如果当前中枢里有互斥组的人，那个组就算被用了)
                    used_groups.add(rule.group)

        available_ops = self.get_available_operators()
        op_by_name = {op.name: op for op in available_ops}

        # 2. 遍历规则尝试填充
        for rule in self.cc_rules:
            if remaining_slots <= 0:
                break

            # --- 互斥检查 ---
            if rule.group and rule.group in used_groups:
                continue

            # --- 空间检查 ---
            if len(rule.operators) > remaining_slots:
                continue

            # --- 干员可用性检查 ---
            valid_rule = True
            for op_name in rule.operators:
                # A. 检查是否拥有
                if op_name not in op_by_name:
                    valid_rule = False;
                    break

                # B. 检查是否当前班次已上班
                if op_name in shift_used_names:
                    valid_rule = False;
                    break

                # =========================================================
                # C. [新增关键修复] 检查累计工作班次 (不能超过2班)
                # =========================================================
                if operator_usage.get(op_name, 0) >= 2:
                    valid_rule = False;
                    break

                # D. 检查练度
                op_obj = op_by_name[op_name]
                if not ignore_elite:
                    req_elite = rule.elite_requirements.get(op_name, 0)
                    if op_obj.elite < req_elite:
                        valid_rule = False;
                        break

            if not valid_rule:
                continue

            # --- 应用规则 ---
            for op_name in rule.operators:
                current_cc_ops.append(op_name)
                shift_used_names.add(op_name)
                operator_usage[op_name] = operator_usage.get(op_name, 0) + 1

            remaining_slots -= len(rule.operators)

            if rule.group:
                used_groups.add(rule.group)

    # 辅助方法：减少代码重复
    def _collect_requirements(self, result, shift_used_names, operator_usage,
                              control_ops, dorm_ops, hire_ops, process_ops):
        """收集 AssignmentResult 中的附属房间需求并更新状态"""

        # 定义一个通用的处理函数
        def process_req_list(req_list, target_set):
            for req in req_list:
                if req.operator not in shift_used_names:
                    # 注意：附属房间干员通常允许重复上班（如中枢），或者有特定排班
                    # 这里简化逻辑：只要没在本班次的其他位置（如制造/贸易）使用即可
                    # 严谨逻辑需判断精力，此处假设附属设施干员可以连续上班或由外部轮换逻辑处理
                    if operator_usage.get(req.operator, 0) < 2:  # 简单限制
                        target_set.add(req.operator)
                        shift_used_names.add(req.operator)
                        operator_usage[req.operator] += 1

        process_req_list(result.control_center_requirements, control_ops)
        process_req_list(result.dormitory_requirements, dorm_ops)
        process_req_list(result.processing_station_requirements, process_ops)  # 收集加工站
        process_req_list(result.hire_requirements, hire_ops)  # 暂时忽略办公室或加对应的集合

    def get_optimal_assignments(self, product_requirements: Dict[str, Dict[str, int]] = None,
                                ignore_elite: bool = False) -> Dict[str, Any]:
        """
        获取最优分配方案
        :param ignore_elite: 是否忽略精英化等级限制（潜在最高效率模式）
        """
        if product_requirements is None:
            product_requirements = self.config_data.get('product_requirements', {
                "trading_stations": {"LMD": 3, "Orundum": 0},
                "manufacturing_stations": {"Pure Gold": 3, "Originium Shard": 0, "Battle Record": 0}
            })

        fiammetta_config = self.config_data.get('Fiammetta', {"enable": False})
        fiammetta_enable = fiammetta_config.get('enable', False)
        # 在潜在模式下，我们假设菲亚梅塔是可用的（只要有）
        fiammetta_available = self.check_fiammetta_available(ignore_elite) if fiammetta_enable else False
        self.fiammetta_targets = self.select_fiammetta_targets() if fiammetta_available else []
        if fiammetta_enable and not self.fiammetta_targets:
            fiammetta_enable = False

        # 初始化产物... (同前)
        trading_products = []
        for product, count in product_requirements['trading_stations'].items():
            trading_products.extend([product] * count)
        for i, workplace in enumerate(self.workplaces['trading_stations']):
            workplace.current_product = trading_products[i] if i < len(trading_products) else ""

        manufacturing_products = []
        for product, count in product_requirements['manufacturing_stations'].items():
            manufacturing_products.extend([product] * count)
        for i, workplace in enumerate(self.workplaces['manufacturing_stations']):
            workplace.current_product = manufacturing_products[i] if i < len(manufacturing_products) else ""

        # --- [修改开始]：构建新的结果头信息 ---

        # 计算基建类型
        power_station_count = 3
        # 拼接数字，例如 243
        building_type_int = int(
            f"{self.trading_stations_count}{self.manufacturing_stations_count}{power_station_count}")

        # 动态生成标题和描述
        if ignore_elite:
            # 潜在模式
            res_title = "潜在最高效率方案"
            res_desc = "忽略干员精英化等级限制，仅根据您持有的干员计算的理论最高收益方案。"
        else:
            # 当前练度模式
            res_title = "当前练度最优方案"
            res_desc = "基于您当前干员的实际练度（精英化等级）生成的最佳排班方案。"

        results = {
            "author": "一只摆烂的42的自动基建排班生成器",  # [新增] 固定作者
            "title": res_title,  # [修改] 动态标题
            "description": res_desc,  # [修改] 动态描述
            "buildingType": building_type_int,  # [新增] 243/252等
            "planTimes": "3班",  # [新增] 固定班次
            "plans": [],
            "raw_results": []
        }
        # --- [修改结束] ---

        operator_usage = {op.name: 0 for op in self.get_available_operators()}

        for shift in range(3):
            current_target = self.fiammetta_targets[
                shift % len(self.fiammetta_targets)] if self.fiammetta_targets else ""

            plan = {
                "name": f"第{shift + 1}班",
                "description": "",
                "Fiammetta": {"enable": fiammetta_enable, "target": current_target, "order": "pre"},
                "rooms": {
                    "trading": [], "manufacture": [], "control": [{"operators": []}],
                    "power": [], "meeting": [{"autofill": True}], "hire": [{"operators": []}],
                    "dormitory": [{"autofill": True} for _ in range(4)], "processing": [{"operators": []}],
                }
            }

            shift_used_names = set()
            control_operators = set()
            dormitory_operators = set()
            hire_operators = set()
            processing_operators = set()

            shift_assignments = []

            # 1. 优化制造站
            for workplace in self.workplaces['manufacturing_stations']:
                result = self.optimize_workplace(workplace, operator_usage, shift_used_names, ignore_elite)
                shift_assignments.append(result)
                plan["rooms"]["manufacture"].append({
                    "operators": [op.name for op in result.optimal_operators],
                    "autofill": False if result.optimal_operators else True,
                    "product": workplace.current_product
                })
                self._collect_requirements(result, shift_used_names, operator_usage,
                                           control_operators, dormitory_operators, hire_operators, processing_operators)

            # 2. 优化贸易站
            for workplace in self.workplaces['trading_stations']:
                result = self.optimize_workplace(workplace, operator_usage, shift_used_names, ignore_elite)
                shift_assignments.append(result)
                plan["rooms"]["trading"].append({
                    "operators": [op.name for op in result.optimal_operators],
                    "autofill": False if result.optimal_operators else True,
                    "product": workplace.current_product
                })
                self._collect_requirements(result, shift_used_names, operator_usage,
                                           control_operators, dormitory_operators, hire_operators, processing_operators)

            # 3. 填充基础附属房间
            plan["rooms"]["control"][0]["operators"] = list(control_operators)

            if dormitory_operators:
                plan["rooms"]["dormitory"][0] = {"operators": list(dormitory_operators), "autofill": True}

            # 4. 优化会客室
            result = self.optimize_workplace(self.workplaces['meeting_room'][0], operator_usage, shift_used_names,
                                             ignore_elite)
            shift_assignments.append(result)
            plan["rooms"]["meeting"][0] = {
                "operators": [op.name for op in result.optimal_operators],
                "autofill": False if result.optimal_operators else True
            }

            # 5. 优化发电站
            for workplace in self.workplaces['power_station']:
                result = self.optimize_workplace(workplace, operator_usage, shift_used_names, ignore_elite)
                shift_assignments.append(result)
                plan["rooms"]["power"].append({
                    "operators": [op.name for op in result.optimal_operators],
                    "autofill": False if result.optimal_operators else True
                })

            # 6. 填充加工站
            if processing_operators:
                valid_process_ops = list(processing_operators)
                plan["rooms"]["processing"][0] = {"operators": [valid_process_ops[0]], "autofill": False}

            # 7. 填充控制中枢
            self.fill_control_center(
                plan,
                shift_used_names,
                operator_usage,
                ignore_elite
            )

            # 计算无人机
            plan["drones"] = self._assign_drones(plan, shift)

            results["plans"].append(plan)
            results["raw_results"].extend(shift_assignments)

        return results

    def _assign_drones(self, plan: Dict[str, Any], shift_index: int) -> Dict[str, Any]:
        """
        根据配置和当前排班计算无人机加速对象
        """
        drone_config = self.config_data.get('drones', {})
        if not drone_config.get('enable', False):
            return {"enable": False, "room": "", "index": 0, "order": "pre"}

        targets = drone_config.get('targets', [])
        if not targets:
            return {"enable": False, "room": "", "index": 0, "order": "pre"}

        # 确定当前班次的目标产物
        # 如果targets只有一个元素，所有班次通用；如果有3个，按班次取
        target_product = targets[0]
        if len(targets) == 3:
            target_product = targets[shift_index]
        elif len(targets) > len(plan):  # 容错
            target_product = targets[shift_index % len(targets)]

        # 定义默认结果
        result = {
            "room": "",
            "index": 0,
            "enable": False,
            "order": drone_config.get("order", "pre")
        }

        # 在排班结果中搜索目标产物所在的房间
        # 1. 搜索贸易站 (rooms["trading"])
        # 注意：plan结构中 key 是 "trading" 和 "manufacture"
        for i, room_data in enumerate(plan["rooms"].get("trading", [])):
            # 这里的 room_data["product"] 是我们在 get_optimal_assignments 里填入的
            if room_data.get("product") == target_product:
                result["room"] = "trading"
                result["index"] = i + 1  # 转换为1-based index
                result["enable"] = True
                return result

        # 2. 搜索制造站 (rooms["manufacture"])
        for i, room_data in enumerate(plan["rooms"].get("manufacture", [])):
            if room_data.get("product") == target_product:
                result["room"] = "manufacture"
                result["index"] = i + 1
                result["enable"] = True
                return result

        # 如果没找到（比如配置了加速赤金，但这班全在造经验书），则 disable
        return result

    def select_fiammetta_targets(self) -> List[str]:
        # 保持原有逻辑
        candidates = ['巫恋', '龙舌兰', '但书']
        selected = []
        for candidate in candidates:
            if candidate in self.operators and self.operators[candidate].own:
                # 简化判断：只要有就行，因为在 ignore_elite 模式下我们希望尽量利用
                if self.operators[candidate].elite >= 2:
                    selected.append(candidate)
                elif self.debug:  # 如果不是E2，记录一下
                    pass
        if len(selected) >= 3: return selected

        # 补位
        trading_rules = [r for r in self.efficiency_rules if r.workplace_type == 'trading_station']
        op_scores = {}
        for rule in trading_rules:
            for op in rule.operators:
                if op in self.operators and self.operators[op].own and op not in selected:
                    # 同样，这里可能选出低练度的，但这符合“潜力”的定义
                    score = rule.synergy_efficiency / len(rule.operators)
                    op_scores[op] = op_scores.get(op, 0) + score
        sorted_ops = sorted(op_scores, key=op_scores.get, reverse=True)
        for op in sorted_ops:
            selected.append(op)
            if len(selected) >= 3: break
        return selected

    def calculate_upgrade_requirements(self, current_assignments: Dict[str, Any],
                                       potential_assignments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        计算练度提升建议，包含效率提升数据，并专门计算菲亚梅塔的收益
        优化：将同一房间/同一方案中需要同时升级的干员打包显示 (Bundling)
        """
        # upgrades key: tuple of ((name, target), ...) sorted by name
        upgrades = {}

        # 专门追踪菲亚梅塔带来的总收益
        fiammetta_gain_total = 0.0
        fiammetta_impact_rooms = set()
        target_set = set(self.fiammetta_targets) if hasattr(self, 'fiammetta_targets') else set()

        current_raw = current_assignments.get("raw_results", [])
        potential_raw = potential_assignments.get("raw_results", [])

        if len(current_raw) != len(potential_raw):
            return []

        for i, pot_res in enumerate(potential_raw):
            curr_res = current_raw[i]
            efficiency_gain = pot_res.total_efficiency - curr_res.total_efficiency

            # 微小误差忽略
            if efficiency_gain <= 0.001:
                continue

            # === 1. 归因分析：这是菲亚梅塔的功劳吗？ ===
            room_ops = [op.name for op in pot_res.optimal_operators]
            is_fiammetta_effect = False

            overlap = target_set.intersection(room_ops)
            if overlap:
                fiammetta_gain_total += efficiency_gain
                fiammetta_impact_rooms.add(pot_res.workplace.name)
                is_fiammetta_effect = True

            # === 2. 细粒度练度需求分析 (按规则归因) ===

            # 获取详细分配记录 (List of {rule, ops, eff, type})
            details = pot_res.assignment_detail

            # 计算当前房间所有建议升级规则的总潜在效率，用于分摊收益
            # 注意：只有真正需要升级的规则才参与分摊
            upgrading_entries = []
            total_upgrading_pot_eff = 0.0

            for detail in details:
                rule = detail['rule']
                ops_in_rule = detail['ops']  # 这一组分配涉及的干员
                rule_eff = detail['eff']
                rule_type = detail.get('type', 'unknown')

                # 收集该规则下的升级需求
                rule_needed_upgrades = {}

                # 1. 自身等级需求
                for op_name in ops_in_rule:
                    # 对于 generic_each，ops_in_rule 只有1人；对于 combo，有多人
                    # 无论哪种，我们都检查每个人的需求
                    req = rule.elite_requirements.get(op_name, 0)
                    if req > 0:
                        rule_needed_upgrades[op_name] = max(rule_needed_upgrades.get(op_name, 0), req)

                # 2. 附属房间需求 (归因到该规则触发的干员)
                # 注意：附属房间需求通常是必须满足的，否则规则不生效。
                # 我们将其归因到该规则的主干员身上（如果是组合，归因到组合；如果是单人，归因到单人）
                # 简化处理：如果附属房间干员需要升级，我们将这个需求也加入到这个规则的升级包里

                for req_list in [rule.requires_control_center, rule.requires_dormitory,
                                 rule.requires_power_station, rule.requires_hire, rule.requires_processing_station]:
                    for r in req_list:
                        rule_needed_upgrades[r.operator] = max(rule_needed_upgrades.get(r.operator, 0),
                                                               r.elite_required)

                # 3. 筛选真正需要升级的干员
                current_rule_bundle = []
                for op_name, target_elite in rule_needed_upgrades.items():
                    if op_name not in self.operators: continue
                    op = self.operators[op_name]
                    if op.elite < target_elite:
                        current_rule_bundle.append({
                            'name': op_name,
                            'current': op.elite,
                            'target': target_elite
                        })

                if current_rule_bundle:
                    # 如果这个规则有需要升级的人，它就是一个升级条目
                    upgrading_entries.append({
                        'bundle': current_rule_bundle,
                        'eff': rule_eff,
                        'type': rule_type
                    })
                    total_upgrading_pot_eff += rule_eff

            # === 3. 分摊收益并记录 ===
            room_name = pot_res.workplace.name

            if total_upgrading_pot_eff > 0:
                for entry in upgrading_entries:
                    # 计算分摊的收益
                    # 逻辑：该规则贡献的效率 / 所有升级规则贡献的总效率 * 房间总提升
                    # 这样保证总和等于房间提升
                    attributed_gain = efficiency_gain * (entry['eff'] / total_upgrading_pot_eff)

                    # 生成唯一键
                    bundle_list = entry['bundle']
                    bundle_list.sort(key=lambda x: x['name'])
                    bundle_key = tuple((item['name'], item['target']) for item in bundle_list)

                    if bundle_key not in upgrades:
                        upgrades[bundle_key] = {
                            'ops': bundle_list,
                            'max_gain': 0.0,
                            'rooms': set(),
                            'is_fiammetta_related': False,
                            'type': entry['type']  # 记录类型
                        }

                    # 累加收益？不，如果是不同房间，应该是 Max 还是 Sum？
                    # 原逻辑是 Max，表示“这个组合在某个房间能带来这么大的提升”。
                    # 如果在多个房间都有效，通常显示最大那个。
                    upgrades[bundle_key]['max_gain'] = max(upgrades[bundle_key]['max_gain'], attributed_gain)
                    upgrades[bundle_key]['rooms'].add(room_name)

                    if is_fiammetta_effect:
                        upgrades[bundle_key]['is_fiammetta_related'] = True

        # === 3. 生成结果列表 ===
        result_list = []

        # A. 菲亚梅塔专项条目
        fiammetta_op = self.operators.get("菲亚梅塔")
        if fiammetta_gain_total > 0.01:
            need_upgrade_fia = False
            curr_fia_elite = 0
            if fiammetta_op:
                curr_fia_elite = fiammetta_op.elite if fiammetta_op.own else -1
                if curr_fia_elite < 2:
                    need_upgrade_fia = True
            else:
                need_upgrade_fia = True

            if need_upgrade_fia:
                result_list.append({
                    'type': 'single',  # 标记类型
                    'name': "菲亚梅塔",
                    'current': curr_fia_elite if curr_fia_elite >= 0 else "未持有",
                    'target': 2,
                    'gain': fiammetta_gain_total,
                    'rooms': f"通过充能 {', '.join(target_set)} 间接提升 {', '.join(fiammetta_impact_rooms)}",
                    'special_type': 'system_core'
                })

        # B. 其他干员组合条目
        for bundle_key, data in upgrades.items():
            # 检查是否只是菲亚梅塔单人且已处理
            if len(data['ops']) == 1 and data['ops'][0]['name'] == "菲亚梅塔" and fiammetta_gain_total > 0.01:
                continue

            # 格式化组合名称和练度
            # 如果是单人
            if len(data['ops']) == 1:
                op_data = data['ops'][0]
                result_list.append({
                    'type': 'single',
                    'name': op_data['name'],
                    'current': op_data['current'],
                    'target': op_data['target'],
                    'gain': data['max_gain'],
                    'rooms': ", ".join(data['rooms']),
                    'special_type': 'normal'
                })
            else:
                # 如果是多人组合
                result_list.append({
                    'type': 'bundle',
                    'ops': data['ops'],  # list of {name, current, target}
                    'gain': data['max_gain'],
                    'rooms': ", ".join(data['rooms']),
                    'special_type': 'normal'
                })

        # 排序：收益高的在前
        result_list.sort(key=lambda x: x['gain'], reverse=True)
        return result_list

    def save_suggestions_to_txt(self, upgrade_list: List[Dict], filename: str = "upgrade_suggestions.txt"):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("               练度提升建议报告\n")
                f.write("=" * 60 + "\n\n")

                if not upgrade_list:
                    f.write("您的队伍已经满足目前最高效率方案的需求，无需提升练度。\n")
                else:
                    # 分离体系建议和普通建议
                    system_suggestions = [x for x in upgrade_list if x.get('special_type') == 'system_core']
                    normal_suggestions = [x for x in upgrade_list if x.get('special_type') != 'system_core']

                    if system_suggestions:
                        f.write("【体系构建建议】\n")
                        f.write("以下干员是提升基建整体效率的核心关键，收益通常涉及多个班次/房间：\n\n")
                        for item in system_suggestions:
                            # 菲亚梅塔的总收益往往很大，格式化显示
                            gain_val = item['gain']
                            gain_str = f"{gain_val * 100:.1f}%" if gain_val < 0.9 else f"{gain_val:.1f}%"

                            # 目前只有菲亚梅塔是体系建议，且结构保持为 single
                            f.write(f"★ 核心干员: {item['name']}\n")
                            current_str = f"精{item['current']}" if isinstance(item['current'], int) else item[
                                'current']
                            f.write(f"  - 练度现状: {current_str} -> 目标: 精{item['target']}\n")
                            f.write(f"  - 体系收益: {item['rooms']}\n")
                            f.write(f"  - 预期总效率提升: +{gain_str} (全天累计)\n")
                            f.write("-" * 40 + "\n")
                        f.write("\n")

                    if normal_suggestions:
                        f.write("【干员练度提升建议】\n")
                        f.write("提升以下干员(或组合)可优化特定房间的效率 (按单房间收益降序)：\n\n")
                        for item in normal_suggestions:
                            gain_val = item['gain']
                            gain_str = f"{gain_val * 100:.1f}%" if gain_val < 0.9 else f"{gain_val:.1f}%"

                            if item.get('type') == 'bundle':
                                op_names = "+".join([op['name'] for op in item['ops']])
                                f.write(f"组合: {op_names}\n")
                                for op in item['ops']:
                                    f.write(f"  - {op['name']}: 精{op['current']} -> 精{op['target']}\n")
                            else:
                                f.write(f"干员: {item['name']}\n")
                                f.write(f"  - 练度现状: 精{item['current']} -> 目标: 精{item['target']}\n")

                            f.write(f"  - 预期收益: {item['rooms']} 效率 +{gain_str}\n")
                            f.write("-" * 40 + "\n")

                import datetime
                f.write(f"\n生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            print(f"成功导出建议至: {filename}")
        except Exception as e:
            print(f"导出文件失败: {e}")

    def display_results(self, current: Dict, potential: Dict, upgrades: List[Dict]):
        print("=" * 60)
        print("               当前练度最优方案")
        print("=" * 60)
        self.display_optimal_assignments(current)

        print("\n" + "=" * 60)
        print("               潜在最高效率方案 (仅考虑持有)")
        print("=" * 60)
        self.display_optimal_assignments(potential)

        print("\n" + "=" * 60)
        print("               练度提升建议")
        print("=" * 60)
        if not upgrades:
            print("您的队伍已经满足目前最高效率方案的需求，无需提升练度。")
        else:
            print(f"检测到 {len(upgrades)} 个干员(或组合)可以通过提升练度来达到更高效率 (按收益排序)：")
            for item in upgrades:
                # 格式化显示效率
                gain_val = item['gain']
                # 判断是小数还是整数百分比
                # Arknights 效率通常 > 1% (值 1)，如果值 < 0.9 则认为是小数格式
                gain_str = f"{gain_val * 100:.1f}%" if gain_val < 0.9 else f"{gain_val:.1f}%"

                if item.get('type') == 'bundle':
                    op_names = "+".join([op['name'] for op in item['ops']])
                    print(f"  [组合提升] {op_names}")
                    for op in item['ops']:
                        print(f"     - {op['name']}: 精{op['current']} -> 精{op['target']}")
                else:
                    print(f"  [提升] {item['name']}: 精{item['current']} -> 精{item['target']}")

                print(f"         收益: {item['rooms']} 效率 +{gain_str}")
        print("=" * 60 + "\n")

    def display_optimal_assignments(self, assignments):
        """显示最优分配方案（三班制）"""

        print("=== 最优工作站分配方案（三班制）===")
        print(f"标题: {assignments['title']}")
        print(f"描述: {assignments['description']}")
        print()

        for plan in assignments['plans']:
            print(f"班次: {plan['name']}")
            print(f"描述: {plan['description']}")
            fiammetta = plan.get('Fiammetta', {})
            if fiammetta.get('enable', False):
                print(f"菲亚梅塔: 启用，目标: {fiammetta.get('target', '无')}")
            else:
                print("菲亚梅塔: 未启用")

            # --- [新增] 显示无人机加速 ---
            drones = plan.get('drones', {})
            if drones.get('enable', False):
                room_map = {'trading': '贸易站', 'manufacture': '制造站'}
                room_cn = room_map.get(drones.get('room'), '未知房间')
                idx = drones.get('index', 0)
                print(f"无人机加速: 启用，目标: {room_cn} {idx}")
            else:
                print("无人机加速: 未启用")

            print("房间分配:")
            for room_type, rooms in plan['rooms'].items():
                if room_type in ['trading', 'manufacture']:
                    name = {'trading': '贸易站', 'manufacture': '制造站'}
                    product_dict = {'LMD': '龙门币', 'Orundum': '合成玉', 'Pure Gold': '赤金',
                                    'Originium Shard': '源石碎片', 'Battle Record': '作战记录'}
                    for i, room in enumerate(rooms):
                        product = product_dict.get(room.get('product', '无'), '无')
                        operators = room.get('operators', [])
                        print(f"  {name[room_type]} {i + 1}: {product}, {operators}")
                elif room_type == 'power':
                    for i, room in enumerate(rooms):
                        operators = room.get('operators', [])
                        print(f"  发电站 {i + 1}: {operators}")
                elif room_type == 'meeting':
                    room = rooms[0]
                    operators = room.get('operators', [])
                    print(f"  会客室: {operators}")
                elif room_type == 'control':
                    operators = rooms[0].get('operators', [])
                    print(f"  控制中枢: {operators}")
                elif room_type == 'dormitory':
                    for i, room in enumerate(rooms):
                        operators = room.get('operators', [])
                        if operators:
                            print(f"  宿舍 {i + 1}: {operators}")
            print()

    # 新增调试打印函数
    def print_loaded_files(self):
        print(f"DEBUG: 已加载的效率文件: {self.efficiency_file}")
        print(f"DEBUG: 已加载的干员文件: {self.operator_file}")

    def print_operator_summary(self):
        owned = [op for op in self.operators.values() if op.own]
        print(f"DEBUG: 干员总数: {len(self.operators)}，已拥有: {len(owned)}")
        if owned:
            sample = ', '.join([f"{op.name}(精{op.elite})" for op in owned[:20]])
            print(f"DEBUG: 已拥有干员示例（最多20）: {sample}")

    def print_efficiency_rules(self, limit: int = 10):
        print(f"DEBUG: 效率规则总数: {len(self.efficiency_rules)}，显示前 {limit} 项")
        for i, rule in enumerate(self.efficiency_rules[:limit]):
            cc = ','.join([f"{r.operator}(精{r.elite_required})" for r in rule.requires_control_center])
            print(
                f"  [{i + 1}] {rule.description} | 类型: {rule.workplace_type} | 干员: {', '.join(rule.operators)} | 协同: {rule.synergy_efficiency}% | 中枢: {cc} | 精英要求: {rule.elite_requirements}")

    def print_workplaces(self):
        ts = self.workplaces.get('trading_stations', [])
        ms = self.workplaces.get('manufacturing_stations', [])
        print(f"DEBUG: 贸易站数量: {len(ts)}，制造站数量: {len(ms)}")
        for w in ts + ms:
            print(f"  - {w.id} {w.name} | 最大干员: {w.max_operators} | 基础效率: {w.base_efficiency}%")

# if __name__ == "__main__":
#     optimizer = WorkplaceOptimizer('efficiency.json', 'operators.json', 'config.json')
#
#     # 1. 获取基于当前练度的方案
#     current_assignments = optimizer.get_optimal_assignments(ignore_elite=False)
#
#     # 2. 获取基于持有情况的潜在最优方案
#     potential_assignments = optimizer.get_optimal_assignments(ignore_elite=True)
#
#     # 3. 计算差异
#     upgrade_list = optimizer.calculate_upgrade_requirements(current_assignments, potential_assignments)
#
#     # 4. 显示结果
#     optimizer.display_results(current_assignments, potential_assignments, upgrade_list)
#
#     # 5. 导出 TXT
#     optimizer.save_suggestions_to_txt(upgrade_list, "upgrade_suggestions.txt")
#
#     # 定义一个辅助函数来清理不需要保存到 JSON 的内部数据（raw_results）
#     def clean_for_json(data):
#         return {k: v for k, v in data.items() if k != 'raw_results'}
#
#
#     # 保存两个文件
#     try:
#         with open('current_assignments.json', 'w', encoding='utf-8') as f:
#             # 这里使用了清理函数，移除了不可序列化的对象
#             json.dump(clean_for_json(current_assignments), f, ensure_ascii=False, indent=2)
#         print("成功保存: current_assignments.json")
#
#         with open('potential_assignments.json', 'w', encoding='utf-8') as f:
#             # 同样清理
#             json.dump(clean_for_json(potential_assignments), f, ensure_ascii=False, indent=2)
#         print("成功保存: potential_assignments.json")
#
#     except TypeError as e:
#         print(f"保存JSON时出错: {e}")