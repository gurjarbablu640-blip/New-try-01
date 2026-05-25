"""
Salesoorja AI Sales Intelligence - Flask Application
=====================================================
Main application factory and entry point.
"""
import logging
from flask import Flask
from flask_cors import CORS

from backend.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.SECRET_KEY

    # Enable CORS for frontend
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    from backend.routes.pipeline import pipeline_bp
    from backend.routes.api import api_bp

    app.register_blueprint(pipeline_bp)
    app.register_blueprint(api_bp)

    # Health check
    @app.route("/health")
    def health():
        return {"status": "healthy", "service": "salesoorja-ai"}

    @app.route("/")
    def index():
        return {
            "service": "Salesoorja AI Sales Intelligence",
            "version": "2.0.0",
            "modules": [
                "Buying Trigger Engine",
                "Hyper-Personalization Engine",
                "AI Outreach Synthesis",
                "Pipeline CRM",
                "Next Best Action Engine",
                "Semantic Search",
                "Lookalike Expansion",
                "ICP Learning Engine",
                "Buying Window Dashboard",
                "A/B Optimizer",
            ]
        }

    logger.info("Salesoorja AI Sales Intelligence app initialized")
    return app


# For direct run
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=settings.DEBUG)
