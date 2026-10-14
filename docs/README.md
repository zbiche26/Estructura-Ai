# levantar servidor backend
uvicorn src.http.app:app --reload

# servidor bakend
http://localhost:8000/api/v1/me

# comnado conexion endpoint
curl http://localhost:8000/api/v1/me
