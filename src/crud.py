from typing import Callable, Generic, TypeVar

from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel, Session, select, create_engine

T = TypeVar("T", bound=SQLModel)


class Crud(Generic[T]):
    """Dynamic CRUD router generator for SQLModel classes.

    Usage:
        crud = Crud(db_url="sqlite:///./gym.db")
        crud.include_model(Exercise)
        crud.include_model(Series)

        app.include_router(crud.get_router())
    """

    def __init__(self, db_url: str):
        self.models: dict[type, dict] = {}
        self.router = APIRouter()
        self._routes: dict[str, Callable] = {}
        self.engine = create_engine(db_url, echo=True, connect_args={"timeout": 5})

    def include_model(self, model: type) -> APIRouter:
        """
        Register a SQLModel class and create CRUD endpoints for it.

        Args:
            model: A SQLModel class (not an instance)

        Returns:
            The router with the newly added endpoints

        Example:
            crud = Crud("sqlite:///./gym.db")
            router = crud.include_model(Exercise)
            app.include_router(router, tags=["Exercises"])
        """
        # Store model info
        self.models[model] = {
            "name": model.__name__,
            "table_name": model.__tablename__
            if hasattr(model, "__tablename__")
            else None,
        }

        # Create the router for this model
        model_router = APIRouter(prefix=f"/{model.__name__}")

        route_specs = [
            ("list", "GET", "", self._create_list_endpoint(model)),
            ("get", "GET", "/{id}", self._create_get_endpoint(model)),
            ("create", "POST", "", self._create_create_endpoint(model)),
            ("update", "PUT", "/{id}", self._create_update_endpoint(model)),
            ("delete", "DELETE", "/{id}", self._create_delete_endpoint(model)),
        ]

        for name, http_method, path, endpoint in route_specs:
            model_router.add_api_route(
                path,
                endpoint,
                methods=[http_method],
                name=f"{model.__name__.lower()}_{name}",
            )

        # Add to main router
        self.router.include_router(model_router)

        return self.router

    def _create_list_endpoint(self, model: type):
        """Create GET /{model} - list all records endpoint."""

        async def handler(limit: int = 100, offset: int = 0):
            """List all records with pagination."""
            with Session(self.engine) as session:
                statement = select(model).offset(offset).limit(limit)
                return session.exec(statement).all()

        return handler

    def _create_get_endpoint(self, model: type):
        """Create GET /{model}/{id} - get single record endpoint."""
        model_name = model.__name__

        def handler(id: int):
            """Get a single record by id."""
            with Session(self.engine) as session:
                result = session.get(model, id)
                if result is None:
                    raise HTTPException(
                        status_code=404, detail=f"{model_name} not found"
                    )
                return result

        return handler

    def _create_create_endpoint(self, model: type):
        """Create POST /{model} - create new record endpoint."""

        def handler(model_data: dict):
            """Create a new record."""
            # Convert dict to model instance
            kwargs = {
                k: v
                for k, v in model_data.items()
                if k in model.model_fields and k != "id"
            }
            new_record = model(**kwargs)

            with Session(self.engine) as session:
                session.add(new_record)
                session.commit()
                session.refresh(new_record)
                return new_record

        return handler

    def _create_update_endpoint(self, model: type):
        """Create PUT /{model}/{id} - update record endpoint."""
        model_name = model.__name__

        def handler(id: int, model_data: dict):
            """Update a record."""
            with Session(self.engine) as session:
                record = session.get(model, id)
                if record is None:
                    raise HTTPException(
                        status_code=404, detail=f"{model_name} not found"
                    )

                # Update fields
                for key, value in model_data.items():
                    if key in model.model_fields and key != "id":
                        setattr(record, key, value)

                session.add(record)
                session.commit()
                session.refresh(record)
                return record

        return handler

    def _create_delete_endpoint(self, model: type):
        """Create DELETE /{model}/{id} - delete record endpoint."""
        model_name = model.__name__

        def handler(id: int):
            """Delete a record."""
            with Session(self.engine) as session:
                record = session.get(model, id)
                if record is None:
                    raise HTTPException(
                        status_code=404, detail=f"{model_name} not found"
                    )

                session.delete(record)
                session.commit()
                return {"message": f"{model_name} deleted successfully"}

        return handler

    def get_router(self) -> APIRouter:
        """
        Get the router with all registered CRUD endpoints.

        Returns:
            APIRouter with all CRUD endpoints for registered models
        """
        return self.router

    def include_all(self, *models: type) -> APIRouter:
        """
        Include multiple models at once.

        Args:
            *models: SQLModel classes to register

        Returns:
            The router with all CRUD endpoints
        """
        for model in models:
            self.include_model(model)
        return self.router
