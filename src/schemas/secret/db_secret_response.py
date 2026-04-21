from pydantic import BaseModel


class DBSecretResponse(BaseModel):
    host: str
    port: int
    username: str
    password: str
    dbname: str
    engine: str
