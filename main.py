from enum import Enum
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, HttpUrl

fake_items_db = [{"item_name": "Foo"}, {"item_name": "Bar"}, {"item_name": "Baz"}]
fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "fakehashedsecret",
        "disabled": False,
    },
    "alice": {
        "username": "alice",
        "full_name": "Alice Wonderson",
        "email": "alice@example.com",
        "hashed_password": "fakehashedsecret2",
        "disabled": True,
    },
}


class BaseUser(BaseModel):
    username: str
    email: EmailStr
    full_name: str | None = None


class CommonQueryParams:
    def __init__(self, q: str | None = None, skip: int = 0, limit: int = 100):
        self.q = q
        self.skip = skip
        self.limit = limit


class Image(BaseModel):
    url: str  # HttpUrl
    name: str


class Item(BaseModel):
    name: str
    description: str | None = Field(default=None, title="The description of the item", max_length=300)
    price: float = Field(ge=0, description="The price must be greater than zero")
    tax: float | None = None
    images: list[Image] | None = None
    tags: set[str] = set()


class ModelName(Enum):
    alexnet = "alexnet"
    resnet = "resnet"
    lenet = "lenet"


class Offer(BaseModel):
    name: str
    description: str | None = None
    price: float
    items: list[Item]


class Tags(Enum):
    items = "items"
    users = "users"


class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserIn(BaseUser):
    password: str


class UserInDB(User):
    hashed_password: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}


CommonsDep = Annotated[dict, Depends(common_parameters)]


def fake_decode_token(token):
    # This doesn't provide any security at all
    # Check the next version
    user = get_user(fake_users_db, token)
    return user


def fake_hash_password(password: str):
    return "fakehashed" + password


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    user = fake_decode_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


app = FastAPI()


@app.put("/items/{item_id}", tags=[Tags.items])
async def change_item(
    item_id: int,
    item: Item | None = None,
    user: BaseUser = None,
    importance: Annotated[int, Body()] = None,
    q: str | None = None,
):
    results = {"item_id": item_id}
    if q:
        results.update({"q": q})
    if item:
        results.update({"item": item})
    if user:
        results.update({"user": user})
    if importance:
        results.update({"importance": importance})
    return results


@app.post("/items/", response_model=Item, tags=[Tags.items])
async def create_item(item: Annotated[Item, Body(embed=True)]) -> dict:
    item_dict = item.dict()
    if item.tax:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict


@app.post("/offers/")
async def create_offer(offer: Offer):
    return offer


@app.post("/user/", status_code=status.HTTP_201_CREATED, tags=[Tags.users])
async def create_user(user: UserIn) -> BaseUser:
    return user


@app.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user_dict = fake_users_db.get(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    user = UserInDB(**user_dict)
    hashed_password = fake_hash_password(form_data.password)
    if not hashed_password == user.hashed_password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    return {"access_token": user.username, "token_type": "bearer"}


@app.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name is ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}


@app.get("/portal", response_model=None)
async def get_portal(teleport: bool = False) -> Response | dict:
    if teleport:
        return RedirectResponse(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    return {"message": "Here's your interdimensional portal."}


@app.get("/users/", tags=[Tags.users])
async def read_users(commons: CommonsDep):
    return commons


@app.get("/items/{item_id}", tags=[Tags.items])
async def read_item(
    item_id: Annotated[int, Path(title="The ID of the item to get", gt=1, le=1000)],
    q: Annotated[str | None, Query(alias="item-query")] = None,
    short: bool = False,
):
    if item_id == 999:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Item 999 forbidden",
            headers={"X-Error": "There goes my error"},
        )
    item = {"item_id": item_id}
    if q:
        item.update({"q": q})
    if not short:
        item.update({"description": "This is an amazing item that has a long description"})
    return item


@app.get("/items/", tags=[Tags.items])
async def read_items(
    skip: int = 0,
    limit: int = 10,
    q: Annotated[
        str | None,
        Query(
            min_length=3,
            max_length=50,
            regex="^fixedquery$",
            title="Query string",
            description="Query string for the items to search in the database that have a good match",
        ),
    ] = None,
    z: Annotated[list[str] | None, Query()] = ["foo", "bar"],
    # commons: Annotated[CommonQueryParams, Depends(CommonQueryParams)] = None,
    commons: Annotated[CommonQueryParams, Depends()] = None,  # shortcut
):
    results = {"items": fake_items_db[skip : skip + limit]}
    if q:
        results.update({"q": q})
    if z:
        results.update({"z": z})
    if commons:
        results.update({"commons": commons})
    return results


@app.get("/files/{file_path:path}")
async def read_file(file_path: str):
    return {"file_path": file_path}


@app.get("/users/me", tags=[Tags.users])
async def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user


@app.get("/")
async def root():
    return {"message": "Hello World"}
