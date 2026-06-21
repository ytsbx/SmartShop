"""
=============================================================================
SmartShop 订单模拟数据生成脚本
=============================================================================
使用 Faker 库批量生成多状态订单演示数据并写入 MySQL。
覆盖 6 种订单状态：pending/paid/shipped/delivered/completed/refunded

运行方式:
    python data/order_mock.py              # 生成默认数量（100条）
    python data/order_mock.py --count 150  # 自定义数量
=============================================================================
"""

import sys
import os
import random
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from faker import Faker
from loguru import logger

from config import MYSQL_CONFIG
from core.logger import setup_logger

setup_logger()

fake = Faker("zh_CN")

# ============================================================================
# 订单模拟数据模板
# ============================================================================

# 客户池
CUSTOMERS = [
    {"name": "张三", "phone": "138****6789", "address": "北京市朝阳区望京街道XX小区3号楼"},
    {"name": "李四", "phone": "139****7890", "address": "上海市浦东新区陆家嘴街道XX大厦12层"},
    {"name": "王五", "phone": "136****8901", "address": "广州市天河区珠江新城XX花园7栋"},
    {"name": "赵六", "phone": "135****9012", "address": "深圳市南山区科技园XX中心15楼"},
    {"name": "孙七", "phone": "137****0123", "address": "杭州市西湖区文三路XX小区2单元"},
]

# 商品池（模拟已售商品，包含多分类）
PRODUCTS = [
    # 数码电子
    {"name": "Apple AirPods Pro 蓝牙耳机", "category": "electronics", "price": 1299},
    {"name": "华为 蓝牙耳机 FreeBuds 5", "category": "electronics", "price": 699},
    {"name": "小米 机械键盘 青轴", "category": "electronics", "price": 249},
    {"name": "罗技 无线鼠标 MX Master 3S", "category": "electronics", "price": 459},
    {"name": "联想 平板电脑 小新Pad Pro", "category": "electronics", "price": 2199},
    {"name": "Sony 桌面音箱 SRS-XB100", "category": "electronics", "price": 349},
    {"name": "Dell 显示器挂灯", "category": "electronics", "price": 199},
    # 服饰鞋包
    {"name": "Nike 运动跑鞋 Air Zoom", "category": "clothing", "price": 649},
    {"name": "优衣库 纯棉圆领T恤 3件装", "category": "clothing", "price": 99},
    {"name": "Adidas 羽绒服 90%白鸭绒", "category": "clothing", "price": 799},
    {"name": "李宁 双肩背包 防水款", "category": "clothing", "price": 159},
    {"name": "UR 牛仔裤 弹力修身", "category": "clothing", "price": 259},
    # 食品饮料
    {"name": "三只松鼠 每日坚果礼盒 30袋", "category": "food", "price": 99},
    {"name": "蒙牛 有机纯牛奶 250ml×24", "category": "food", "price": 79},
    {"name": "雀巢 冻干咖啡粉 速溶", "category": "food", "price": 89},
    {"name": "稻香村 蛋黄酥礼盒 12枚", "category": "food", "price": 59},
    # 美妆个护
    {"name": "欧莱雅 防晒霜 SPF50+", "category": "beauty", "price": 99},
    {"name": "兰蔻 精华液 小黑瓶 30ml", "category": "beauty", "price": 499},
    {"name": "完美日记 口红 哑光6色", "category": "beauty", "price": 79},
    {"name": "花西子 保湿面膜 20片", "category": "beauty", "price": 69},
    # 家居生活
    {"name": "MUJI 乳胶枕 人体工学", "category": "home", "price": 199},
    {"name": "苏泊尔 空气炸锅 4.5L", "category": "home", "price": 359},
    {"name": "九阳 保温杯 316不锈钢", "category": "home", "price": 89},
    {"name": "小米有品 扫地机器人", "category": "home", "price": 1999},
    # 运动户外
    {"name": "迪卡侬 瑜伽垫 加厚NBR", "category": "sports", "price": 79},
    {"name": "YONEX 羽毛球拍 碳素双拍", "category": "sports", "price": 299},
    {"name": "Keep 跑步机 家用折叠", "category": "sports", "price": 2699},
    {"name": "探路者 户外帐篷 3-4人", "category": "sports", "price": 499},
]

# 物流公司池
LOGISTICS_COMPANIES = ["顺丰速运", "京东物流", "中通快递", "圆通速递", "韵达快递", "EMS", "极兔速递", "申通快递"]

# 订单状态流转关系
STATUS_FLOW = {
    "pending": "待支付",
    "paid": "已支付",
    "shipped": "运输中",
    "delivered": "已签收",
    "completed": "已完成",
    "refunded": "已退款",
}


def generate_order_data(count: int = 100) -> list:
    """生成订单模拟数据"""
    records = []
    today = date.today()
    used_order_nos = set()

    for i in range(count):
        # 随机选择客户
        customer = random.choice(CUSTOMERS)

        # 随机选择商品（可重复）
        product = random.choice(PRODUCTS)
        quantity = random.randint(1, 3)
        unit_price = product["price"]
        total_price = round(unit_price * quantity, 2)

        # 订单状态（按概率分布，偏向已完成和已签收）
        status = random.choices(
            ["pending", "paid", "shipped", "delivered", "completed", "refunded"],
            weights=[5, 10, 15, 25, 35, 10],
            k=1,
        )[0]

        # 订单日期：近30天随机
        days_ago = random.randint(1, 30)
        order_date = today - timedelta(days=days_ago)

        # 物流信息（仅 shipped/delivered 有）
        logistics_company = ""
        tracking_no = ""
        if status in ("shipped", "delivered", "completed"):
            logistics_company = random.choice(LOGISTICS_COMPANIES)
            tracking_no = f"{random.choice(['SF','JD','YT','YD'])}{random.randint(10000000000, 99999999999)}"

        # 生成唯一订单号
        while True:
            order_no = f"ORD{order_date.strftime('%Y%m%d')}{random.randint(1000, 9999)}"
            if order_no not in used_order_nos:
                used_order_nos.add(order_no)
                break

        records.append({
            "order_no": order_no,
            "product_name": product["name"],
            "category": product["category"],
            "customer_name": customer["name"],
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "status": status,
            "logistics_company": logistics_company,
            "tracking_no": tracking_no,
            "order_date": order_date,
            "delivery_address": customer["address"],
            "phone": customer["phone"],
            "customer_note": _random_note(status),
        })

    # 按订单日期倒序排序
    records.sort(key=lambda x: x["order_date"], reverse=True)
    return records


def _random_note(status: str) -> str:
    """根据订单状态生成随机备注"""
    notes = {
        "pending": random.choice(["", "请尽快发货", "拍错了能改吗"]),
        "paid": random.choice(["", "已付款，请发货", "修改了地址"]),
        "shipped": random.choice(["", "发货挺快的", "物流有点慢"]),
        "delivered": random.choice(["", "收到了，不错", "包装完好"]),
        "completed": random.choice(["", "好评！", "质量很好，会回购"]),
        "refunded": random.choice(["", "不合适退了", "尺寸偏小"]),
    }
    return notes.get(status, "")


def insert_records(records: list) -> int:
    """批量插入订单记录到 MySQL"""
    if not records:
        return 0

    conn = None
    count = 0
    try:
        conn = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"],
            charset=MYSQL_CONFIG["charset"],
            connect_timeout=MYSQL_CONFIG["connect_timeout"],
        )

        sql = (
            "INSERT INTO order_info "
            "(order_no, product_name, category, customer_name, quantity, "
            " unit_price, total_price, status, logistics_company, tracking_no, "
            " order_date, delivery_address, phone, customer_note) "
            "VALUES (%(order_no)s, %(product_name)s, %(category)s, %(customer_name)s, "
            " %(quantity)s, %(unit_price)s, %(total_price)s, %(status)s, "
            " %(logistics_company)s, %(tracking_no)s, %(order_date)s, "
            " %(delivery_address)s, %(phone)s, %(customer_note)s)"
        )

        with conn.cursor() as cursor:
            cursor.executemany(sql, records)
            count = cursor.rowcount

        conn.commit()
        logger.info("订单数据入库完成 | 写入 {} 条", count)

    except Exception as e:
        logger.error("订单数据入库失败: {}", str(e))
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    return count


def main(count: int = 100):
    """主函数：生成全部订单模拟数据并入库"""
    logger.info("=== 开始生成订单模拟数据 | 目标 {} 条 ===", count)

    records = generate_order_data(count)
    total = insert_records(records)

    # 按状态统计
    from collections import Counter
    status_count = Counter(r["status"] for r in records)
    for status, label in STATUS_FLOW.items():
        logger.info("  {} ({}): {} 条", label, status, status_count.get(status, 0))

    # 按客户统计
    customer_count = Counter(r["customer_name"] for r in records)
    for name, cnt in customer_count.most_common():
        logger.info("  客户 {}: {} 单", name, cnt)

    logger.info("=== 订单模拟数据生成完毕 | 总计 {} 条 ===", total)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SmartShop 订单模拟数据生成器")
    parser.add_argument("--count", type=int, default=100, help="生成的订单数量")
    args = parser.parse_args()

    main(count=args.count)
