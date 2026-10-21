from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

class AccountCreate(BaseModel):
    prenom: str = Field(min_length=1, max_length=100)
    nom: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    numero_tel: str | None = Field(default=None, max_length=30)
    adresse: str | None = None

class PasswordCheck(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class BankAccountCreate(BaseModel):
    id_compte: UUID
    iban_reference: str = Field(min_length=5, max_length=100)
    solde: float = Field(default=0, ge=0)
    devise: str = Field(default="EUR", min_length=3, max_length=3)

class CardCreate(BaseModel):
    id_compte_bancaire: UUID
    card_token: str = Field(min_length=5, max_length=255)
    numero_carte: str = Field(pattern=r"^[0-9]{12,19}$")
    nom_carte: str = Field(min_length=1, max_length=150)
    expiration: str = Field(pattern=r"^(0[1-9]|1[0-2])/([0-9]{2}|[0-9]{4})$")
