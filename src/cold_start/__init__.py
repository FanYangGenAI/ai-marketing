"""Cold-start ingestion: attachments manifest, product profile, understanding job."""

from src.cold_start.retrieval import load_product_context_for_agents

__all__ = ["load_product_context_for_agents"]
