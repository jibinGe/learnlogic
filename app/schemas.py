from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List, TypeVar, Generic
from datetime import datetime
from .models import UserType
from fastapi import Form, File, UploadFile
from .models import EventStatus
from enum import Enum as PyEnum
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from decimal import Decimal
import uuid

class RecordBase(BaseModel):
    customer_email: EmailStr
    data: Dict

class RecordCreate(RecordBase):
    pass

class RecordUpdate(BaseModel):
    customer_email: Optional[EmailStr] = None
    data: Optional[Dict] = None

class RecordInDB(RecordBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    email: str
    full_name: str
    title: Optional[str] = None
    job_title: Optional[str] = None
    school: Optional[str] = None
    billing_address: Optional[str] = None
    user_type: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    user_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_type: Optional[UserType] = None

class WorkBase(BaseModel):
    name: str
    data: Dict[str, Any]
    user_id: int

class WorkCreate(WorkBase):
    pass

class WorkInDB(WorkBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True

class TestimonialBase(BaseModel):
    picture_url: str
    stars: int
    matter: str
    type: str

class Testimonial(TestimonialBase):
    id: int
    created_at: datetime
    user_id: int
    name: str
    

    class Config:
        from_attributes = True

class TestimonialCreate(BaseModel):
    stars: int
    matter: str
    user_id: int
    name: str

    @classmethod
    def as_form(
        cls,
        stars: int = Form(...),
        matter: str = Form(...),
        user_id: int = Form(...),
    ):
        return cls(stars=stars, matter=matter, user_id=user_id)

class TestimonialPagination(BaseModel):
    items: List[Testimonial]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        from_attributes = True

class FileData(BaseModel):
    url: str
    file_type: str
    original_name: str
    category: str

class ThemeFileData(BaseModel):
    images: List[FileData] = []
    pdfs: List[FileData] = []
    docs: List[FileData] = []
    zips: List[FileData] = []

class ThemeBase(BaseModel):
    name: str
    price: str
    data: Optional[ThemeFileData] = ThemeFileData()
    type: Optional[str] = ''

class ThemeCreate(ThemeBase):
    pass

class Theme(ThemeBase):
    id: int
    created_at: datetime
    resource_id: int

    class Config:
        from_attributes = True

class ThemeResponse(Theme):
    @property
    def file_count(self) -> int:
        if not self.data:
            return 0
        return (
            len(self.data.images) +
            len(self.data.pdfs) +
            len(self.data.docs)
        )

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ResourceBase(BaseModel):
    name: str
    data: Dict[str, Any]

class ResourceCreate(ResourceBase):
    pass

class ResourceUpdate(ResourceBase):
    name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class ResourceWithThemes(ResourceBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    themes: List[ThemeResponse] = []

    class Config:
        from_attributes = True

class Resource(ResourceBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class ResourceMinimal(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

class FileDataEvent(BaseModel):
    url: str
    file_type: str
    original_name: str
    category: str

class TrainerBase(BaseModel):
    name: str
    bio: str
    photo: Optional[FileDataEvent] = None

class EventBase(BaseModel):
    title: str
    date_month: str
    date_day: str
    date_year: str
    location: str
    price: str
    time: Optional[str] = None
    type: str
    color: str
    teachers: List[str]
    why_attend: Optional[Dict[str, Any]] = {}
    programme: Optional[Dict[str, Any]] = {}
    trainers: Optional[Dict[str, List[TrainerBase]]] = {"items": []}
    # Add new fields here
    qualification: Optional[str] = None
    exam_board: Optional[str] = None
    subject: Optional[str] = None
    is_hidden: Optional[bool]


class EventUpdateAdmin(BaseModel):
    status: Optional[EventStatus] = None
    total_seats: Optional[int] = None
    is_hidden: Optional[bool] = None

class EventCreate(EventBase):
    pass

class Event(EventBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    total_seats: Optional[int] = None
    seats_booked: int = 0
    status: Optional[EventStatus] = None

    class Config:
        orm_mode = True


################## Cart #####################

class CartBase(BaseModel):
    stored_ids: List[int]

class CartCreate(CartBase):
    pass

class CartResponse(CartBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class BillingAddressUpdate(BaseModel):
    billing_address: str

class BillingAddressResponse(BaseModel):
    user_id: int
    billing_address: str

    class Config:
        orm_mode = True

#################Interest

# T = TypeVar('T')

class ItemTypeEnum(str, PyEnum):
    resource = "resource"
    event = "event"
    others = "others"

class InterestCreate(BaseModel):
    interest_id: int
    item_type: ItemTypeEnum

class Interest(BaseModel):
    id: int
    interest_id: int
    item_type: str
    user_id: int

    class Config:
        from_attributes = True

class InterestWithDetails(BaseModel):
    id: int
    interest_id: int
    item_type: str
    user_id: int
    user_details: Optional[Dict[str, Any]] = None
    details: Optional[Dict[str, Any]] = None

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

class EmailRequest(BaseModel):
    to_addresses: List[EmailStr]
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_address: EmailStr
    cc_addresses: Optional[List[EmailStr]] = None
    bcc_addresses: Optional[List[EmailStr]] = None

class EmailResponse(BaseModel):
    message_id: str
    status: str
    message: str

##################### stripe_schemas #####################

class BillingAddress(BaseModel):
    line1: str = Field(..., min_length=1, max_length=100)
    line2: Optional[str] = Field(None, max_length=100)
    city: str = Field(..., min_length=1, max_length=50)
    state: Optional[str] = Field(None, max_length=50)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")


class CartItem(BaseModel):
    item_id: str
    name: str
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., ge=0)
    item_type: str  # 'resource' or 'event'


class CreatePaymentIntentRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Amount in main currency unit (pounds, dollars, etc.)")
    currency: str = Field(default="gbp", description="Currency code (gbp, usd, eur, inr)")
    cart_items: List[CartItem] = Field(..., min_items=1)
    billing_address: Optional[BillingAddress] = None
    save_payment_method: bool = Field(default=True, description="Whether to save payment method for future use")
    
    @validator('currency')
    def validate_currency(cls, v):
        supported = ['gbp', 'usd', 'eur', 'inr']
        if v.lower() not in supported:
            raise ValueError(f'Currency must be one of: {", ".join(supported)}')
        return v.lower()
    
    @validator('amount')
    def validate_amount(cls, v):
        if v < Decimal('0.50'):
            raise ValueError('Minimum payment amount is 0.50')
        return v


class PaymentIntentResponse(BaseModel):
    payment_intent_id: str
    client_secret: str
    customer_id: str
    amount: Decimal
    currency: str
    status: str
    supported_payment_methods: List[str] = ["card"]


class ConfirmPaymentRequest(BaseModel):
    payment_intent_id: str = Field(..., min_length=1)
    billing_address: Optional[BillingAddress] = None


class PaymentConfirmationResponse(BaseModel):
    success: bool
    payment_intent_id: str
    purchase_id: Optional[uuid.UUID] = None
    amount: Decimal
    currency: str
    message: str
    payment_method: Optional[Dict[str, Any]] = None


class SavedPaymentMethod(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    country: Optional[str] = None
    is_default: bool = False


class PaymentMethodsResponse(BaseModel):
    payment_methods: List[SavedPaymentMethod]
    default_method_id: Optional[str] = None


class PaymentWithSavedMethodRequest(BaseModel):
    payment_method_id: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="gbp")
    cart_items: List[CartItem] = Field(..., min_items=1)
    billing_address: Optional[BillingAddress] = None
    
    @validator('currency')
    def validate_currency(cls, v):
        supported = ['gbp', 'usd', 'eur', 'inr']
        if v.lower() not in supported:
            raise ValueError(f'Currency must be one of: {", ".join(supported)}')
        return v.lower()


class StripeWebhookEvent(BaseModel):
    id: str
    object: str
    api_version: Optional[str] = None
    created: int
    data: Dict[str, Any]
    livemode: bool
    pending_webhooks: int
    request: Optional[Dict[str, Any]] = None
    type: str


class CurrencyInfo(BaseModel):
    code: str
    symbol: str
    name: str
    is_primary: bool


class SupportedCurrenciesResponse(BaseModel):
    currencies: List[CurrencyInfo]
    default_currency: str


#### Multipart upload part ###

class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str
    folder: str  # e.g., "events", "themes", "testimonials"
    subfolder: Optional[str] = None  # e.g., "trainers", "images", "pdfs"
    max_file_size: Optional[int] = 10 * 1024 * 1024 * 1024  # 10GB default
    
    @validator('content_type')
    def validate_content_type(cls, v):
        allowed_types = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "application/pdf",
            "application/zip",
            "application/x-zip-compressed",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
            "application/vnd.ms-powerpoint",  # .ppt
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
            "application/vnd.ms-excel",  # .xls
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        ]
        if v not in allowed_types:
            raise ValueError(f'Content type {v} not allowed')
        return v

class PresignedUrlResponse(BaseModel):
    presigned_url: str
    fields: Dict[str, Any]
    object_key: str
    final_url: str
    expires_in: int = 3600

# Multipart Upload Models
class MultipartUploadRequest(BaseModel):
    filename: str
    content_type: str
    folder: str
    subfolder: Optional[str] = None
    file_size: int  # Total file size in bytes
    
    @validator('file_size')
    def validate_file_size(cls, v):
        if v > 10 * 1024 * 1024 * 1024:  # 10GB limit
            raise ValueError('File size exceeds 10GB limit')
        return v

class MultipartUploadResponse(BaseModel):
    upload_id: str
    object_key: str
    part_size: int = 5 * 1024 * 1024  # 5MB parts
    total_parts: int

class MultipartPartRequest(BaseModel):
    upload_id: str
    object_key: str
    part_number: int

class MultipartPartResponse(BaseModel):
    part_number: int
    presigned_url: str
    expires_in: int = 3600

class MultipartCompleteRequest(BaseModel):
    upload_id: str
    object_key: str
    parts: List[Dict[str, Any]]  # [{"PartNumber": 1, "ETag": "etag"}]

class MultipartCompleteResponse(BaseModel):
    final_url: str
    object_key: str

# File Upload Confirmation Models
class FileUploadConfirmation(BaseModel):
    object_key: str
    original_filename: str
    file_size: Optional[int] = None
    content_type: str

class EventCreateRequest(BaseModel):
    title: str
    date_month: str
    date_day: Optional[str] = None
    date_year: str
    location: str
    price: str
    type: str
    time: str
    color: str
    teachers: List[str]
    qualification: Optional[str] = None
    exam_board: Optional[str] = None
    subject: Optional[str] = None
    why_attend: Dict[str, Any]  # JSON object instead of string
    programme: Dict[str, Any]   # JSON object instead of string
    trainer_files: Optional[List[FileUploadConfirmation]] = None

class ThemeCreateRequest(BaseModel):
    name: str
    price: str
    type: str
    resource_id: int
    files: List[FileUploadConfirmation]

class TestimonialCreateRequest(BaseModel):
    name: str
    stars: int
    matter: str
    type: str
    user_id: int
    picture_file: FileUploadConfirmation

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: str

class ContactFormBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    school_name: str = Field(..., min_length=1, max_length=500)
    position: str = Field(..., min_length=1, max_length=100)
    message: Optional[str] = None


class ContactFormCreate(ContactFormBase):
    pass


class ContactFormUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    school_name: Optional[str] = Field(None, min_length=1, max_length=500)
    position: Optional[str] = Field(None, min_length=1, max_length=100)
    message: Optional[str] = None


class ContactForm(ContactFormBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


