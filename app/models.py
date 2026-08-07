from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum, Boolean, ForeignKey, Table, Float, Text
from sqlalchemy.sql import func
from .database import Base
import enum
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from sqlalchemy.types import TypeDecorator, String
import json

class UserType(str, enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    TUTOR = "tutor"

class StringList(TypeDecorator):
    impl = String
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    title = Column(String)
    full_name = Column(String)
    job_title = Column(String, nullable = True)
    school = Column(String, nullable = True)
    billing_address = Column(String, nullable=True)
    user_type = Column(Enum(UserType))
    is_active = Column(Boolean, default=True)
    stripe_customer_id = Column(String, nullable=True, index=True)

    cart_data = relationship("Cart", back_populates="user", cascade="all, delete-orphan")
    tutor_profile = relationship("TutorProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

class TutorProfile(Base):
    __tablename__ = "tutor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Contact & location
    mobile_number = Column(String, nullable=False)
    country = Column(String, nullable=False)
    city = Column(String, nullable=False)

    # Teaching profile
    subjects = Column(StringList, nullable=False, default=list)
    exam_boards = Column(StringList, nullable=False, default=list)
    qualifications = Column(StringList, nullable=False, default=list)
    languages = Column(StringList, nullable=True, default=list)
    teaching_method = Column(String, nullable=False)          # Online / Face-to-face / Both
    years_of_experience = Column(String, nullable=False)
    price_per_hour = Column(Float, nullable=False)
    about_me = Column(Text, nullable=False)

    # Avatar / profile picture (optional, S3 URL)
    avatar_url = Column(String, nullable=True)

    is_subscribed = Column(Boolean, default=False)
    stripe_subscription_id = Column(String, nullable=True)
    subscribed_at = Column(DateTime(timezone=True), nullable=True)
    # End of the paid period after cancellation — tutor stays visible until this date
    subscription_ends_at = Column(DateTime(timezone=True), nullable=True)

    # Impression counter — incremented when a visitor views a private (non-subscribed) profile card
    profile_impressions = Column(Integer, default=0, nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="tutor_profile")


class Testimonial(Base):
    __tablename__ = "testimonials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    picture_url = Column(String)
    stars = Column(Integer)
    matter = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String)

class Theme(Base):
    __tablename__ = 'themes'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    data = Column(JSON)
    price = Column(String)
    type = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resource_id = Column(Integer, ForeignKey('resources.id'))
    
    resource = relationship("Resources", back_populates="themes")

class Resources(Base):
    __tablename__ = 'resources'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    themes = relationship("Theme", back_populates="resource")




class EventStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UPCOMING = "upcoming"
    ON_HOLD = "on_hold"
    ALL_SEATS_BOOKED = "all_seats_booked"

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    date_month = Column(String, nullable=False)
    date_day = Column(String, nullable=False)
    date_year = Column(String, nullable=False)
    location = Column(String, nullable=False)
    price = Column(String, nullable=False)
    type = Column(String, nullable=False)
    time = Column(String, nullable=True)
    color = Column(String, nullable=False)
    teachers = Column(StringList, nullable=False, default=list)
    why_attend = Column(JSON, default=dict)
    programme = Column(JSON, default=dict)
    trainers = Column(JSON, default=lambda: {"items": []})
    qualification = Column(String, nullable=True)
    exam_board = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    is_hidden = Column(Boolean, nullable=False, default=False)
    total_seats = Column(Integer, nullable=True)  # Optional for now
    seats_booked = Column(Integer, default=0)
    status = Column(Enum(EventStatus), default=EventStatus.ACTIVE)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Cart(Base):
    __tablename__ = "cart"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="cart_data")
    cart_items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("cart.id"))
    item_type = Column(Enum("resource", "event", name="item_types"), nullable=False)
    
    # For resources
    theme_id = Column(Integer, nullable=True)
    resource_id = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True)
    
    # For events
    event_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    cart = relationship("Cart", back_populates="cart_items")

    def is_resource(self):
        return self.item_type == "resource"

    def is_event(self):
        return self.item_type == "event"
    
class PurchaseStatus(str, enum.Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"
    REFUNDED = "refunded"

class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    total_amount = Column(Float)
    transaction_id = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    status = Column(Enum(PurchaseStatus), default=PurchaseStatus.PENDING)

    payment_intent_id = Column(String, nullable=True, index=True)
    payment_method_id = Column(String, nullable=True)
    payment_status = Column(String, default='pending')  # pending, succeeded, failed, cancelled
    stripe_charge_id = Column(String, nullable=True)
    payment_metadata = Column(Text, nullable=True)  # JSON string for additional payment data
    billing_address = Column(Text, nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="purchases")
    purchase_items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
    item_type = Column(Enum("resource", "event", name="purchase_item_types"), nullable=False)
    
    # For resources
    theme_id = Column(Integer, nullable=True)
    resource_id = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True)
    
    # For events
    event_id = Column(Integer, nullable=True)
    
    # Price at time of purchase
    price = Column(Float, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    purchase = relationship("Purchase", back_populates="purchase_items")

    def is_resource(self):
        return self.item_type == "resource"

    def is_event(self):
        return self.item_type == "event"
    

class Interest(Base):
    __tablename__ = "interest"
    id = Column(Integer, primary_key=True, index=True)
    interest_id = Column(Integer)
    item_type = Column(Enum("resource", "event","others", name="interest_item_types"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ContactForm(Base):
    __tablename__ = "contact_forms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    school_name = Column(String(500), nullable=False)
    position = Column(String(100), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


