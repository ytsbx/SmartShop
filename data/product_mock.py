"""
=============================================================================
SmartShop 商品模拟数据生成脚本
=============================================================================
使用 Faker 库批量生成多分类商品演示数据并写入 MySQL。
覆盖 6 大品类：数码电子 / 服饰鞋包 / 食品饮料 / 美妆个护 / 家居生活 / 运动户外

运行方式:
    python data/product_mock.py              # 生成默认数量（每类10条）
    python data/product_mock.py --count 15   # 自定义每类数量
=============================================================================
"""

import sys
import os
import random
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from faker import Faker
from loguru import logger

from config import MYSQL_CONFIG
from core.logger import setup_logger

setup_logger()

fake = Faker("zh_CN")

# ============================================================================
# 商品分类与品牌池
# ============================================================================
CATEGORIES = {
    "electronics": {
        "name": "数码电子",
        "brands": ["Apple", "华为", "小米", "Sony", "Bose", "罗技", "Dell", "联想", "三星", "OPPO"],
        "products": [
            ("蓝牙耳机", "降噪", 99, 1999),
            ("机械键盘", "青轴/红轴/茶轴", 129, 899),
            ("无线鼠标", "办公/游戏", 29, 599),
            ("手机充电器", "快充 GaN", 39, 199),
            ("平板电脑", "11英寸 2K屏", 1499, 4999),
            ("智能手表", "运动健康监测", 399, 2599),
            ("移动电源", "20000mAh", 79, 299),
            ("USB-C 扩展坞", "7合1", 99, 399),
            ("桌面音箱", "蓝牙5.3", 149, 999),
            ("显示器挂灯", "护眼 RA98", 89, 349),
        ],
    },
    "clothing": {
        "name": "服饰鞋包",
        "brands": ["Nike", "Adidas", "优衣库", "ZARA", "H&M", "李宁", "安踏", "UR", "太平鸟", "海澜之家"],
        "products": [
            ("纯棉圆领T恤", "男女同款 多色可选", 39, 199),
            ("轻薄羽绒服", "90%白鸭绒", 299, 999),
            ("运动跑鞋", "缓震回弹", 199, 899),
            ("牛仔裤", "弹力修身", 99, 399),
            ("双肩背包", "防水 大容量", 79, 349),
            ("防晒衣", "UPF50+", 89, 299),
            ("羊绒围巾", "100%山羊绒", 149, 599),
            ("休闲卫衣", "加绒保暖", 99, 349),
            ("商务衬衫", "免烫抗皱", 129, 499),
            ("帆布鞋", "经典款 低帮", 69, 259),
        ],
    },
    "food": {
        "name": "食品饮料",
        "brands": ["三只松鼠", "良品铺子", "百草味", "蒙牛", "伊利", "农夫山泉", "雀巢", "星巴克", "五芳斋", "稻香村"],
        "products": [
            ("每日坚果礼盒", "30袋混合装", 49, 169),
            ("有机纯牛奶", "250ml×24盒", 59, 129),
            ("冻干咖啡粉", "速溶 冷热双泡", 39, 149),
            ("蛋黄酥礼盒", "12枚装 手工制作", 29, 99),
            ("牛肉干", "麻辣/五香 500g", 39, 89),
            ("普洱茶饼", "357g 古树春茶", 99, 499),
            ("燕麦片", "即食 1kg装", 19, 59),
            ("坚果大礼包", "8袋 年货礼盒", 79, 199),
            ("手撕面包", "整箱 1kg", 19, 49),
            ("黑巧克力", "72%可可 礼盒装", 29, 129),
        ],
    },
    "beauty": {
        "name": "美妆个护",
        "brands": ["欧莱雅", "兰蔻", "资生堂", "珀莱雅", "完美日记", "花西子", "雅诗兰黛", "SK-II", "薇诺娜", "Colorkey"],
        "products": [
            ("防晒霜", "SPF50+ PA+++", 49, 199),
            ("保湿面膜", "玻尿酸补水 20片", 39, 149),
            ("口红", "哑光/滋润 多色号", 59, 259),
            ("精华液", "烟酰胺亮肤 30ml", 89, 399),
            ("洗面奶", "氨基酸温和洁面", 29, 129),
            ("粉底液", "遮瑕持妆 30ml", 79, 299),
            ("眼霜", "淡化细纹 15g", 99, 399),
            ("卸妆水", "温和不刺激 500ml", 39, 139),
            ("香水", "持久淡香 50ml", 129, 599),
            ("沐浴露", "持久留香 1L", 29, 89),
        ],
    },
    "home": {
        "name": "家居生活",
        "brands": ["MUJI", "网易严选", "宜家", "苏泊尔", "九阳", "小米有品", "南极人", "水星家纺", "双立人", "摩飞"],
        "products": [
            ("乳胶枕", "天然乳胶 人体工学", 89, 399),
            ("保温杯", "316不锈钢 500ml", 49, 199),
            ("空气炸锅", "4.5L 大容量", 199, 599),
            ("四件套", "纯棉 1.8m床", 149, 499),
            ("扫地机器人", "激光导航 自动集尘", 999, 2999),
            ("吹风机", "负离子护发 2000W", 79, 349),
            ("不粘锅", "麦饭石 炒锅 32cm", 89, 299),
            ("台灯", "LED护眼 无极调光", 59, 249),
            ("收纳箱", "塑料 大号 3件套", 39, 129),
            ("电动牙刷", "声波震动 IPX7", 99, 399),
        ],
    },
    "sports": {
        "name": "运动户外",
        "brands": ["迪卡侬", "探路者", "骆驼", "Keep", "YONEX", "李宁", "Nike", "特步", "Northland", "始祖鸟"],
        "products": [
            ("瑜伽垫", "加厚防滑 NBR", 39, 149),
            ("跑步机", "家用折叠 静音", 1499, 3999),
            ("羽毛球拍", "碳素纤维 双拍", 129, 499),
            ("户外帐篷", "3-4人 防雨防晒", 199, 799),
            ("运动水壶", "Tritan材质 750ml", 29, 99),
            ("速干T恤", "吸湿排汗 UPF30", 49, 169),
            ("登山杖", "铝合金 可伸缩", 59, 199),
            ("游泳镜", "防雾 高清 近视可选", 39, 159),
            ("护膝", "运动防护 半月板支撑", 29, 129),
            ("跳绳", "轴承竞速 可计数", 19, 79),
        ],
    },
}

# 店铺名称池
STORE_NAMES = [
    "官方旗舰店", "品牌直营店", "优品生活馆", "数码潮品店",
    "全球购专营店", "品质好货店", "会员精选店", "潮流前线店",
    "好物严选店", "精品百货店",
]

# 规格后缀（按分类）
SPECS_POOL = {
    "electronics": ["标准版", "高配版", "128G", "256G", "黑色", "白色", "银色", "深空灰"],
    "clothing": ["S", "M", "L", "XL", "XXL", "黑色", "白色", "灰色", "蓝色", "卡其色"],
    "food": ["袋装", "盒装", "礼盒装", "家庭装", "分享装"],
    "beauty": ["滋润型", "清爽型", "自然色", "象牙白", "30ml", "50ml", "100ml"],
    "home": ["大号", "中号", "小号", "白色", "灰色", "蓝色", "粉色"],
    "sports": ["标准码", "加长款", "轻量版", "专业版", "入门版"],
}


def generate_product_data(count_per_category: int = 10) -> list:
    """生成全部商品模拟数据"""
    records = []
    today = date.today()

    for cat_key, cat_info in CATEGORIES.items():
        cat_name = cat_info["name"]
        brands = cat_info["brands"]
        products = cat_info["products"]
        specs_pool = SPECS_POOL.get(cat_key, ["标准版"])

        for i, (product_name, product_desc, min_price, max_price) in enumerate(products[:count_per_category]):
            brand = brands[i % len(brands)]
            price = round(random.uniform(min_price, max_price), 2)

            # 原价：约 70% 的商品有折扣
            if random.random() < 0.7:
                original_price = round(price * random.uniform(1.1, 1.6), 2)
            else:
                original_price = price

            # 规格
            spec1 = random.choice(specs_pool)
            spec2 = random.choice(specs_pool)
            while spec2 == spec1:
                spec2 = random.choice(specs_pool)
            specs = f"{spec1}/{spec2}"

            # 关键词
            keywords = f"{product_name},{brand},{product_desc},{cat_name}"

            records.append({
                "name": f"{brand} {product_name}",
                "category": cat_key,
                "brand": brand,
                "price": price,
                "original_price": original_price,
                "stock": random.randint(0, 5000),
                "rating": round(random.uniform(3.5, 5.0), 1),
                "sales_count": random.randint(10, 50000),
                "description": f"{brand}正品 {product_name} — {product_desc}。品质保证，售后无忧。",
                "image_url": f"https://img.smartshop.demo/{cat_key}/{cat_key}_{i+1}.jpg",
                "store_name": random.choice(STORE_NAMES),
                "specs": specs,
                "keywords": keywords,
            })

    # 按评分降序排序（高评分商品靠前）
    records.sort(key=lambda x: x["rating"], reverse=True)
    return records


def insert_records(records: list) -> int:
    """批量插入商品记录到 MySQL"""
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
            "INSERT INTO product_info "
            "(name, category, brand, price, original_price, stock, rating, sales_count, "
            " description, image_url, store_name, specs, keywords) "
            "VALUES (%(name)s, %(category)s, %(brand)s, %(price)s, %(original_price)s, "
            " %(stock)s, %(rating)s, %(sales_count)s, %(description)s, %(image_url)s, "
            " %(store_name)s, %(specs)s, %(keywords)s)"
        )

        with conn.cursor() as cursor:
            cursor.executemany(sql, records)
            count = cursor.rowcount

        conn.commit()
        logger.info("商品数据入库完成 | 写入 {} 条", count)

    except Exception as e:
        logger.error("商品数据入库失败: {}", str(e))
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    return count


def main(count: int = 10):
    """主函数：生成全部商品模拟数据并入库"""
    total_categories = len(CATEGORIES)
    logger.info("=== 开始生成商品模拟数据 | 每类 {} 条 | 共 {} 类 ===", count, total_categories)

    records = generate_product_data(count)
    total = insert_records(records)

    # 按分类统计
    from collections import Counter
    cat_count = Counter(r["category"] for r in records)
    for cat_key, cat_info in CATEGORIES.items():
        logger.info("  {} ({}): {} 条", cat_info["name"], cat_key, cat_count.get(cat_key, 0))

    logger.info("=== 商品模拟数据生成完毕 | 总计 {} 条 ===", total)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SmartShop 商品模拟数据生成器")
    parser.add_argument("--count", type=int, default=10, help="每类商品的生成数量")
    args = parser.parse_args()

    main(count=args.count)
