from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 一次存檔最多變更的商品數（加入 + 移出）。
MAX_STORE_PRODUCT_BATCH = 2000


class StoreProductItem(BaseModel):
    """門市商品清單編輯畫面的一列：商品目錄的一筆商品，附上是否已在清單。"""

    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    sku: str
    barcode: str
    brand: str
    name: str
    scale: Optional[str] = None
    list_price: int = Field(..., alias="listPrice")
    image_url: Optional[str] = Field(None, alias="imageUrl")
    in_list: bool = Field(..., alias="inList")
    added_at: Optional[datetime] = Field(None, alias="addedAt")
    added_by: Optional[str] = Field(None, alias="addedBy")


class StoreProductPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    store_name: str = Field(..., alias="storeName")
    product_scope: Literal["all", "list"] = Field(..., alias="productScope")
    # 清單內未刪除的商品數（不受 keyword / inList 篩選影響）。
    listed_total: int = Field(..., alias="listedTotal")
    items: List[StoreProductItem]
    page: int
    page_size: int = Field(..., alias="pageSize")
    total: int


class StoreProductBatchRequest(BaseModel):
    """勾選畫面按「存檔」一次送出：add 加入清單、remove 移出清單，同一個交易套用。"""

    model_config = ConfigDict(populate_by_name=True)

    add: List[str] = Field(default_factory=list, max_length=MAX_STORE_PRODUCT_BATCH)
    remove: List[str] = Field(default_factory=list, max_length=MAX_STORE_PRODUCT_BATCH)

    @model_validator(mode="after")
    def _check(self) -> "StoreProductBatchRequest":
        add = {v.strip() for v in self.add if v and v.strip()}
        remove = {v.strip() for v in self.remove if v and v.strip()}
        if not add and not remove:
            raise ValueError("add 與 remove 至少要有一個商品")
        if len(add) + len(remove) > MAX_STORE_PRODUCT_BATCH:
            raise ValueError(f"一次最多變更 {MAX_STORE_PRODUCT_BATCH} 個商品")
        both = add & remove
        if both:
            raise ValueError(f"同一個商品不能同時加入又移出 (ID: {sorted(both)[0]})")
        return self


class CopyStoreProductsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_store_name: str = Field(..., alias="sourceStoreName", min_length=1)
    # false：加到現有清單（已有的不重複）；true：先清空本門市清單再複製。
    replace: bool = False


class StoreProductChangeResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    store_name: str = Field(..., alias="storeName")
    product_scope: Literal["all", "list"] = Field(..., alias="productScope")
    # 這次實際新增或移除的筆數（已存在／本來就不在清單的不算）。changed = added + removed。
    changed: int
    added: int = 0
    removed: int = 0
    listed_total: int = Field(..., alias="listedTotal")
