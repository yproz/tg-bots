"""SQLAlchemy 2.0 модели – единственный источник истины структуры БД."""
from sqlalchemy import (
    Column, Integer, BigInteger, Text, Numeric, Date, ForeignKey, UniqueConstraint, Boolean, DateTime
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ----------------------------- основные таблицы -----------------------------
class Client(Base):
    __tablename__ = "clients"

    id             = Column(Text, primary_key=True)          # "SEB"
    name           = Column(Text, nullable=False)            # человекочитаемое
    group_chat_id  = Column(BigInteger, nullable=False)      # куда слать отчёты
    parser_api_key = Column(Text, nullable=True)             # ключ для парсера API
    omni_url       = Column(Text, nullable=True)             # URL OmniCRM
    omni_api_key   = Column(Text, nullable=True)             # ключ OmniCRM

    accounts = relationship("Account", back_populates="client")
    products = relationship("Product", back_populates="client")


class Account(Base):
    __tablename__ = "accounts"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    client_id      = Column(Text, ForeignKey("clients.id"))
    market         = Column(Text, nullable=False)          # ozon / wb
    account_id     = Column(Text, nullable=False)          # "fm"
    api_key        = Column(Text, nullable=False)
    region         = Column(Text, nullable=False)
    ozon_client_id = Column(Text, nullable=True)
    market_price   = Column(Text, nullable=True)           # имя поля OmniCRM
    showcase_price = Column(Text, nullable=True)
    topic_id       = Column(BigInteger, nullable=True)      # ID треда для уведомлений

    client   = relationship("Client", back_populates="accounts")
    products = relationship("Product", back_populates="account")

    __table_args__ = (UniqueConstraint("client_id", "market", "account_id",
                                       name="uq_account"),)


class Product(Base):
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    client_id    = Column(Text, ForeignKey("clients.id"))
    account_id   = Column(Integer, ForeignKey("accounts.id"))
    product_code = Column(Text, nullable=False)            # offer_id / vendorCode
    product_name = Column(Text, nullable=False)
    product_link = Column(Text, nullable=True)             # ссылка на товар в маркетплейсе

    client  = relationship("Client", back_populates="products")
    account = relationship("Account", back_populates="products")

    __table_args__ = (UniqueConstraint("account_id", "product_code",
                                       name="uq_product"),)


class Order(Base):
    """Таблица для отслеживания заказов в парсер"""
    __tablename__ = "orders"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    client_id    = Column(Text, ForeignKey("clients.id"))
    task_id      = Column(Text, nullable=False)            # ID задачи в парсере (userlabel)
    region       = Column(Text, nullable=False)            # регион
    market       = Column(Text, nullable=False)            # ozon / wb
    status       = Column(Text, nullable=False)            # pending / completed / failed
    report_url   = Column(Text, nullable=True)             # URL отчета
    created_at   = Column(DateTime, nullable=False)
    updated_at   = Column(DateTime, nullable=False)
    
    __table_args__ = (UniqueConstraint("task_id", name="uq_order"),)


class Result(Base):
    """Таблица для результатов парсинга"""
    __tablename__ = "results"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    client_id      = Column(Text, ForeignKey("clients.id"))
    task_id        = Column(Text, nullable=False)          # ID задачи в парсере
    product_id     = Column(Integer, ForeignKey("products.id"))
    account_id     = Column(Integer, ForeignKey("accounts.id"))
    product_code   = Column(Text, nullable=False)          # offer_id / vendorCode
    product_name   = Column(Text, nullable=False)
    product_link   = Column(Text, nullable=True)           # ссылка на товар
    market_price   = Column(Numeric, nullable=True)        # цена из маркетплейса (Ozon API)
    showcase_price = Column(Numeric, nullable=True)        # цена на витрине (из парсера)
    timestamp      = Column(DateTime, nullable=False)      # время создания записи
    
    __table_args__ = (UniqueConstraint("client_id", "task_id", "product_code",
                                       name="uq_result"),) 