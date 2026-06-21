-- ============================================================================
-- SmartShop 数据库初始化脚本
-- 适用于 MySQL 8.0
-- 执行方式: mysql -u root -p < sql/init_shop.sql
-- ============================================================================

-- 创建数据库（如不存在）
CREATE DATABASE IF NOT EXISTS smartshop
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE smartshop;

-- ============================================================================
-- 1. 商品信息表 product_info
-- ============================================================================
CREATE TABLE IF NOT EXISTS product_info (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(200)   NOT NULL COMMENT '商品名称',
    category        VARCHAR(50)    NOT NULL COMMENT '商品分类：electronics/clothing/food/beauty/home/sports',
    brand           VARCHAR(100)   DEFAULT '' COMMENT '品牌',
    price           DECIMAL(10,2)  NOT NULL COMMENT '售价（元）',
    original_price  DECIMAL(10,2)  DEFAULT NULL COMMENT '原价（元），用于展示折扣',
    stock           INT            DEFAULT 0 COMMENT '库存数量',
    rating          DECIMAL(2,1)   DEFAULT 5.0 COMMENT '评分 1.0-5.0',
    sales_count     INT            DEFAULT 0 COMMENT '历史销量',
    description     TEXT           COMMENT '商品描述',
    image_url       VARCHAR(500)   DEFAULT '' COMMENT '图片链接（模拟）',
    store_name      VARCHAR(100)   DEFAULT '' COMMENT '店铺名称',
    specs           VARCHAR(200)   DEFAULT '' COMMENT '规格参数',
    keywords        VARCHAR(300)   DEFAULT '' COMMENT '搜索关键词（逗号分隔）',
    updated_at      DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',

    INDEX idx_category_price (category, price),
    INDEX idx_rating (rating),
    INDEX idx_sales (sales_count),
    FULLTEXT INDEX ft_name_keywords (name, keywords)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品信息表';

-- ============================================================================
-- 2. 订单信息表 order_info
-- ============================================================================
CREATE TABLE IF NOT EXISTS order_info (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_no          VARCHAR(32)    NOT NULL COMMENT '订单编号（唯一）',
    product_name      VARCHAR(200)   NOT NULL COMMENT '商品名称',
    category          VARCHAR(50)    DEFAULT '' COMMENT '商品分类',
    customer_name     VARCHAR(50)    NOT NULL COMMENT '客户姓名',
    quantity          INT            DEFAULT 1 COMMENT '购买数量',
    unit_price        DECIMAL(10,2)  NOT NULL COMMENT '商品单价（元）',
    total_price       DECIMAL(10,2)  NOT NULL COMMENT '订单总价（元）',
    status            VARCHAR(20)    DEFAULT 'pending' COMMENT '订单状态：pending/paid/shipped/delivered/completed/refunded',
    logistics_company VARCHAR(50)    DEFAULT '' COMMENT '物流公司',
    tracking_no       VARCHAR(50)    DEFAULT '' COMMENT '物流单号',
    order_date        DATE           NOT NULL COMMENT '下单日期',
    delivery_address  VARCHAR(200)   DEFAULT '' COMMENT '收货地址',
    phone             VARCHAR(20)    DEFAULT '' COMMENT '联系电话',
    customer_note     VARCHAR(300)   DEFAULT '' COMMENT '订单备注',
    updated_at        DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',

    UNIQUE KEY uk_order_no (order_no),
    INDEX idx_customer (customer_name),
    INDEX idx_status (status),
    INDEX idx_order_date (order_date),
    INDEX idx_customer_date (customer_name, order_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单信息表';
