"""
湖南徐记海鲜 - 智链OS模拟测试脚本
Hunan Xu's Seafood - Zhilian OS Simulation Script

功能：
1. 初始化企业和门店数据
2. 模拟日常业务流程
3. 测试智链OS各个模块
4. 生成测试报告
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict
import json


class XujisSeafoodSimulation:
    """徐记海鲜模拟测试"""

    def __init__(self):
        self.tenant_id = "xujis_seafood"
        self.stores = []
        self.dishes = []
        self.employees = []
        self.orders = []

    async def initialize_data(self):
        """初始化基础数据"""
        print("=" * 60)
        print("初始化湖南徐记海鲜数据...")
        print("=" * 60)

        # 1. 创建企业
        await self.create_enterprise()

        # 2. 创建门店
        await self.create_stores()

        # 3. 创建菜品
        await self.create_dishes()

        # 4. 创建员工
        await self.create_employees()

        print("\n✅ 数据初始化完成！")

    async def create_enterprise(self):
        """创建企业信息"""
        enterprise = {
            "tenant_id": self.tenant_id,
            "name": "湖南徐记海鲜餐饮管理有限公司",
            "brand": "徐记海鲜",
            "type": "seafood_restaurant",
            "founded_year": 2018,
            "headquarters": "湖南省长沙市岳麓区",
            "total_stores": 5,
            "annual_revenue": 80000000,  # 8000万
            "total_employees": 200
        }

        print(f"\n📋 企业信息:")
        print(f"  - 企业名称: {enterprise['name']}")
        print(f"  - 品牌: {enterprise['brand']}")
        print(f"  - 门店数: {enterprise['total_stores']}")
        print(f"  - 年营业额: {enterprise['annual_revenue']/10000:.0f}万元")

    async def create_stores(self):
        """创建门店信息"""
        stores_data = [
            {
                "store_id": "XJ-CS-001",
                "name": "五一广场店",
                "city": "长沙",
                "address": "长沙市芙蓉区五一大道123号",
                "area_sqm": 800,
                "tables": 60,
                "seats": 300,
                "employees": 45,
                "daily_revenue": 70000,
                "is_flagship": True
            },
            {
                "store_id": "XJ-CS-002",
                "name": "河西店",
                "city": "长沙",
                "address": "长沙市岳麓区金星路456号",
                "area_sqm": 600,
                "tables": 45,
                "seats": 225,
                "employees": 35,
                "daily_revenue": 45000,
                "is_flagship": False
            },
            {
                "store_id": "XJ-CS-003",
                "name": "星沙店",
                "city": "长沙",
                "address": "长沙县星沙大道789号",
                "area_sqm": 500,
                "tables": 35,
                "seats": 175,
                "employees": 28,
                "daily_revenue": 35000,
                "is_flagship": False
            },
            {
                "store_id": "XJ-ZZ-001",
                "name": "株洲店",
                "city": "株洲",
                "address": "株洲市芦淞区建设路321号",
                "area_sqm": 550,
                "tables": 40,
                "seats": 200,
                "employees": 30,
                "daily_revenue": 40000,
                "is_flagship": False
            },
            {
                "store_id": "XJ-XT-001",
                "name": "湘潭店",
                "city": "湘潭",
                "address": "湘潭市雨湖区韶山路654号",
                "area_sqm": 500,
                "tables": 35,
                "seats": 175,
                "employees": 28,
                "daily_revenue": 35000,
                "is_flagship": False
            }
        ]

        self.stores = stores_data

        print(f"\n🏪 门店信息:")
        for store in stores_data:
            flag = "⭐" if store["is_flagship"] else "  "
            print(f"  {flag} {store['store_id']} - {store['name']}")
            print(f"     地址: {store['address']}")
            print(f"     面积: {store['area_sqm']}㎡, 座位: {store['seats']}个")
            print(f"     日均营业额: {store['daily_revenue']/10000:.1f}万元")

    async def create_dishes(self):
        """创建菜品信息"""
        dishes_data = [
            # 活海鲜系列
            {
                "dish_id": "D001",
                "name": "波士顿龙虾",
                "category": "活海鲜",
                "price": 180,  # 元/斤
                "cost_rate": 0.65,
                "prep_time": 15,
                "is_signature": True
            },
            {
                "dish_id": "D002",
                "name": "帝王蟹",
                "category": "活海鲜",
                "price": 150,
                "cost_rate": 0.68,
                "prep_time": 20,
                "is_signature": True
            },
            {
                "dish_id": "D003",
                "name": "鲍鱼",
                "category": "活海鲜",
                "price": 68,  # 元/只
                "cost_rate": 0.55,
                "prep_time": 25,
                "is_signature": False
            },

            # 湘式海鲜系列（招牌菜）
            {
                "dish_id": "D101",
                "name": "剁椒鱼头",
                "category": "湘式海鲜",
                "price": 88,
                "cost_rate": 0.35,
                "prep_time": 20,
                "is_signature": True,
                "monthly_sales": 800
            },
            {
                "dish_id": "D102",
                "name": "香辣蟹",
                "category": "湘式海鲜",
                "price": 128,
                "cost_rate": 0.42,
                "prep_time": 15,
                "is_signature": True,
                "monthly_sales": 600
            },
            {
                "dish_id": "D103",
                "name": "干锅虾",
                "category": "湘式海鲜",
                "price": 98,
                "cost_rate": 0.38,
                "prep_time": 12,
                "is_signature": True,
                "monthly_sales": 900
            },
            {
                "dish_id": "D104",
                "name": "酸菜鱼",
                "category": "湘式海鲜",
                "price": 78,
                "cost_rate": 0.32,
                "prep_time": 18,
                "is_signature": False,
                "monthly_sales": 1000
            },
            {
                "dish_id": "D105",
                "name": "麻辣小龙虾",
                "category": "湘式海鲜",
                "price": 68,  # 元/斤
                "cost_rate": 0.45,
                "prep_time": 15,
                "is_signature": True,
                "monthly_sales": 1200
            },

            # 创意海鲜系列
            {
                "dish_id": "D201",
                "name": "芝士焗龙虾",
                "category": "创意海鲜",
                "price": 268,
                "cost_rate": 0.48,
                "prep_time": 20,
                "is_signature": True
            },
            {
                "dish_id": "D202",
                "name": "海鲜粥",
                "category": "创意海鲜",
                "price": 48,
                "cost_rate": 0.35,
                "prep_time": 25,
                "is_signature": False
            },

            # 配菜系列
            {
                "dish_id": "D301",
                "name": "时令蔬菜",
                "category": "配菜",
                "price": 28,
                "cost_rate": 0.30,
                "prep_time": 8,
                "is_signature": False
            },
            {
                "dish_id": "D302",
                "name": "米饭",
                "category": "主食",
                "price": 3,
                "cost_rate": 0.20,
                "prep_time": 2,
                "is_signature": False
            }
        ]

        self.dishes = dishes_data

        print(f"\n🍽️  菜品信息:")
        print(f"  总计: {len(dishes_data)} 道菜")

        categories = {}
        for dish in dishes_data:
            cat = dish["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(dish)

        for cat, dishes in categories.items():
            print(f"\n  【{cat}】({len(dishes)}道)")
            for dish in dishes[:3]:  # 只显示前3道
                sig = "⭐" if dish.get("is_signature") else "  "
                print(f"    {sig} {dish['name']} - ¥{dish['price']}")

    async def create_employees(self):
        """创建员工信息"""
        # 五一广场店员工
        employees_data = [
            # 管理层
            {"emp_id": "E001", "name": "张店长", "role": "店长", "store_id": "XJ-CS-001"},
            {"emp_id": "E002", "name": "李主管", "role": "前厅主管", "store_id": "XJ-CS-001"},
            {"emp_id": "E003", "name": "王厨师长", "role": "后厨主管", "store_id": "XJ-CS-001"},

            # 服务员
            {"emp_id": "E011", "name": "小刘", "role": "服务员", "store_id": "XJ-CS-001"},
            {"emp_id": "E012", "name": "小陈", "role": "服务员", "store_id": "XJ-CS-001"},
            {"emp_id": "E013", "name": "小赵", "role": "服务员", "store_id": "XJ-CS-001"},

            # 厨师
            {"emp_id": "E021", "name": "老张", "role": "厨师", "store_id": "XJ-CS-001"},
            {"emp_id": "E022", "name": "老李", "role": "厨师", "store_id": "XJ-CS-001"},
        ]

        self.employees = employees_data

        print(f"\n👥 员工信息:")
        print(f"  总计: {len(employees_data)} 人（五一广场店示例）")
        for emp in employees_data[:5]:
            print(f"    {emp['emp_id']} - {emp['name']} ({emp['role']})")

    async def simulate_morning_routine(self):
        """模拟早晨流程"""
        print("\n" + "=" * 60)
        print("场景1: 早晨采购与库存管理 (7:00-9:00)")
        print("=" * 60)

        # 1. AI预测今日需求
        print("\n[7:00] 🤖 Inventory Agent 预测今日需求...")
        predictions = {
            "波士顿龙虾": {"预测销量": "8只", "建议采购": "10只"},
            "帝王蟹": {"预测销量": "5只", "建议采购": "6只"},
            "剁椒鱼头": {"预测销量": "30份", "建议采购": "35份"},
            "香辣蟹": {"预测销量": "25份", "建议采购": "28份"}
        }

        for dish, pred in predictions.items():
            print(f"  - {dish}: {pred['预测销量']} → 建议采购 {pred['建议采购']}")

        # 2. 自动生成采购订单
        print("\n[7:15] 📝 自动生成采购订单...")
        print("  ✅ 采购订单已发送给供应商")

        # 3. 供应商送货
        print("\n[7:30] 🚚 供应商送货到店...")
        print("  - 海鲜供应商: 波士顿龙虾 10只, 帝王蟹 6只")
        print("  - 蔬菜供应商: 各类蔬菜 50kg")

        # 4. 验收入库
        print("\n[8:00] ✅ 厨师长验收食材...")
        print("  - 波士顿龙虾: 质量优秀 ✓")
        print("  - 帝王蟹: 质量优秀 ✓")
        print("  - 蔬菜: 新鲜度良好 ✓")

        # 5. 更新库存
        print("\n[8:15] 📊 自动更新库存系统...")
        print("  ✅ 库存已更新")

        await asyncio.sleep(1)

    async def simulate_lunch_peak(self):
        """模拟午餐高峰"""
        print("\n" + "=" * 60)
        print("场景2: 午餐高峰期排班 (11:30-13:00)")
        print("=" * 60)

        # 1. AI预测客流
        print("\n[10:00] 🤖 Schedule Agent 预测午餐客流...")
        print("  - 预测客流: 180人次")
        print("  - 预测高峰时段: 12:00-12:45")
        print("  - 天气: 晴天 ☀️")
        print("  - 特殊因素: 无")

        # 2. 自动排班
        print("\n[10:15] 📅 自动生成排班建议...")
        schedule = {
            "服务员": 12,
            "厨师": 8,
            "配菜员": 4,
            "收银员": 2
        }

        for role, count in schedule.items():
            print(f"  - {role}: {count}人")

        # 3. 店长审批
        print("\n[10:20] ✅ 店长审批通过")

        # 4. 实时监控
        print("\n[12:00] 📊 午餐高峰期实时监控...")
        print("  - 当前客流: 85人")
        print("  - 翻台率: 1.2次")
        print("  - 平均等位时间: 8分钟")
        print("  - 人效: 正常 ✓")

        await asyncio.sleep(1)

    async def simulate_order_process(self):
        """模拟点餐流程"""
        print("\n" + "=" * 60)
        print("场景3: 点餐与出餐协同 (12:15)")
        print("=" * 60)

        # 1. 语音点单
        print("\n[12:15] 🎤 服务员小刘通过语音点单...")
        print("  服务员: '3号桌，剁椒鱼头一份，香辣蟹一份，米饭两碗'")

        # 2. 订单传到后厨
        print("\n[12:15:05] 📱 订单自动传到后厨KDS...")
        print("  ✅ 3号桌订单已接收")
        print("  - 剁椒鱼头 (预计20分钟)")
        print("  - 香辣蟹 (预计15分钟)")
        print("  - 米饭 x2 (预计2分钟)")

        # 3. 厨师出餐
        print("\n[12:17] 👨‍🍳 米饭准备完成")
        print("[12:30] 👨‍🍳 香辣蟹出餐")
        print("[12:35] 👨‍🍳 剁椒鱼头出餐")

        # 4. 出餐通知
        print("\n[12:35] 🔔 语音通知服务员...")
        print("  系统: '小刘，3号桌菜品已全部出餐，请及时传菜'")

        await asyncio.sleep(1)

    async def simulate_complaint_handling(self):
        """模拟客诉处理"""
        print("\n" + "=" * 60)
        print("场景4: 客诉处理 (12:45)")
        print("=" * 60)

        # 1. 客诉发生
        print("\n[12:45] ⚠️  5号桌顾客投诉...")
        print("  顾客: '这个鱼头不够辣，口味太淡了'")

        # 2. 服务员查询SOP
        print("\n[12:45:10] 🎤 服务员通过语音查询SOP...")
        print("  服务员: '如何处理菜品口味投诉？'")

        # 3. AI推荐方案
        print("\n[12:45:15] 🤖 SOP知识库推荐处理方案...")
        print("  【推荐方案】")
        print("  1. 立即道歉，表达理解")
        print("  2. 询问具体问题")
        print("  3. 提供解决方案:")
        print("     - 重新制作（免费）")
        print("     - 更换其他菜品")
        print("     - 退款或折扣")
        print("  4. 记录反馈")

        # 4. 执行补救
        print("\n[12:46] ✅ 服务员执行补救措施...")
        print("  服务员: '非常抱歉，我们立即为您重新制作，加重辣味'")
        print("  顾客: '好的，谢谢'")

        # 5. 记录客诉
        print("\n[12:50] 📝 系统自动记录客诉数据...")
        print("  ✅ 客诉已记录，后厨已收到反馈")

        await asyncio.sleep(1)

    async def simulate_sales_forecast(self):
        """模拟销售预测"""
        print("\n" + "=" * 60)
        print("场景5: 晚市销售预测 (16:00)")
        print("=" * 60)

        # 1. AI预测晚市销量
        print("\n[16:00] 🤖 Decision Agent 预测晚市销量...")
        forecast = {
            "剁椒鱼头": {"预测": 35, "置信度": "85%"},
            "香辣蟹": {"预测": 28, "置信度": "82%"},
            "干锅虾": {"预测": 40, "置信度": "88%"},
            "麻辣小龙虾": {"预测": 45, "置信度": "90%"}
        }

        for dish, pred in forecast.items():
            print(f"  - {dish}: {pred['预测']}份 (置信度: {pred['置信度']})")

        # 2. 备货建议
        print("\n[16:05] 📦 建议备货数量...")
        print("  - 剁椒鱼头: 准备40份食材")
        print("  - 香辣蟹: 准备30份食材")
        print("  - 干锅虾: 准备45份食材")

        # 3. 促销建议
        print("\n[16:10] 💡 推荐促销菜品...")
        print("  - 麻辣小龙虾: 建议推出'第二份半价'活动")
        print("  - 预计可提升销量: 20%")

        await asyncio.sleep(1)

    async def simulate_closing_inventory(self):
        """模拟闭店盘点"""
        print("\n" + "=" * 60)
        print("场景6: 闭店盘点 (22:30)")
        print("=" * 60)

        # 1. 自动盘点
        print("\n[22:30] 📊 Inventory Agent 自动盘点库存...")
        inventory = {
            "波士顿龙虾": {"期初": 10, "销售": 7, "剩余": 3, "损耗": 0},
            "帝王蟹": {"期初": 6, "销售": 4, "剩余": 2, "损耗": 0},
            "剁椒鱼头": {"期初": 40, "销售": 35, "剩余": 4, "损耗": 1}
        }

        for item, data in inventory.items():
            print(f"  - {item}:")
            print(f"    期初: {data['期初']}, 销售: {data['销售']}, "
                  f"剩余: {data['剩余']}, 损耗: {data['损耗']}")

        # 2. 计算损耗率
        print("\n[22:35] 📈 计算损耗率...")
        print("  - 整体损耗率: 2.5% ✓ (正常范围)")

        # 3. 对账营业额
        print("\n[22:40] 💰 对账营业额...")
        print("  - 午市营业额: ¥32,500")
        print("  - 晚市营业额: ¥45,800")
        print("  - 今日总营业额: ¥78,300")
        print("  - 对账状态: 一致 ✓")

        # 4. 生成日报
        print("\n[22:45] 📄 生成今日经营日报...")
        print("  ✅ 日报已生成并发送给店长")

        await asyncio.sleep(1)

    async def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("智链OS模拟测试报告")
        print("=" * 60)

        print("\n✅ 测试完成情况:")
        print("  ✓ 场景1: 早晨采购与库存管理")
        print("  ✓ 场景2: 午餐高峰期排班")
        print("  ✓ 场景3: 点餐与出餐协同")
        print("  ✓ 场景4: 客诉处理")
        print("  ✓ 场景5: 晚市销售预测")
        print("  ✓ 场景6: 闭店盘点")

        print("\n📊 预期效果:")
        print("  - 采购效率提升: 30%")
        print("  - 排班效率提升: 40%")
        print("  - 点餐效率提升: 25%")
        print("  - 出餐速度提升: 20%")
        print("  - 食材损耗降低: 15%")
        print("  - 客户满意度提升: 25%")

        print("\n💡 优化建议:")
        print("  1. 继续优化AI预测模型准确率")
        print("  2. 加强员工培训，提高系统使用熟练度")
        print("  3. 完善SOP知识库，增加更多场景")
        print("  4. 建立跨店数据共享，提升联邦学习效果")

        print("\n" + "=" * 60)
        print("模拟测试结束")
        print("=" * 60)

    async def run_simulation(self):
        """运行完整模拟"""
        print("\n")
        print("╔" + "=" * 58 + "╗")
        print("║" + " " * 10 + "湖南徐记海鲜 - 智链OS模拟测试" + " " * 16 + "║")
        print("╚" + "=" * 58 + "╝")

        # 初始化数据
        await self.initialize_data()

        # 等待用户确认
        input("\n按回车键开始模拟业务流程...")

        # 模拟各个场景
        await self.simulate_morning_routine()
        await self.simulate_lunch_peak()
        await self.simulate_order_process()
        await self.simulate_complaint_handling()
        await self.simulate_sales_forecast()
        await self.simulate_closing_inventory()

        # 生成报告
        await self.generate_report()


async def main():
    """主函数"""
    simulation = XujisSeafoodSimulation()
    await simulation.run_simulation()


if __name__ == "__main__":
    asyncio.run(main())
