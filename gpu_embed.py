"""Stage 2: turn frames and queries into vectors in the same space."""

from runpod_flash import Endpoint, GpuGroup


@Endpoint(
    name="ctrlf-clip",
    gpu=GpuGroup.ADA_24,
    workers=(0, 2),
    idle_timeout=300,
    dependencies=["torch", "transformers==5.15.1", "pillow"],
)
class Clip:
    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        # ViT-B/32 is ~600MB at 512 dimensions and provisions in seconds, which
        # is what you want while proving the pipeline. For better retrieval swap
        # this one string for "google/siglip-so400m-patch14-384".
        model_id = "openai/clip-vit-base-patch32"
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_id).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(model_id)
        print(f"[ctrlf-clip] loaded {model_id} on {self.device}")


    def _as_embeddings(self, out, projection):

        if hasattr(out, "shape"):                      
            return out
        for attr in ("text_embeds", "image_embeds"):   
            v = getattr(out, attr, None)
            if v is not None:
                return v
        pooled = getattr(out, "pooler_output", None)
        if pooled is None:
            raise TypeError(f"cannot extract embeddings from {type(out).__name__}")
        projection_dim = getattr(self.model.config, "projection_dim", None)
        if projection_dim is not None and pooled.shape[-1] == projection_dim:
            return pooled                             
        return projection(pooled)                      

    async def embed_images(self, input_data: dict) -> dict:
        """base64 JPEGs in, L2-normalised vectors out.

        input_data: {"images_b64": [str, ...], "batch_size": int}
        """
        import base64
        import io

        from PIL import Image

        images_b64 = input_data.get("images_b64") or []
        if not images_b64:
            return {"error": "images_b64 is required and must be non-empty"}
        batch_size = int(input_data.get("batch_size", 64))

        vectors = []
        for i in range(0, len(images_b64), batch_size):
            chunk = images_b64[i : i + batch_size]
            images = [
                Image.open(io.BytesIO(base64.b64decode(b))).convert("RGB") for b in chunk
            ]
            inputs = self.processor(images=images, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                feats = self._as_embeddings(
                    self.model.get_image_features(**inputs), self.model.visual_projection
                )
            feats = feats / feats.norm(dim=-1, keepdim=True)
            vectors.extend(feats.cpu().tolist())

        return {"vectors": vectors, "count": len(vectors), "dim": len(vectors[0])}

    async def embed_text(self, input_data: dict) -> dict:

        texts = input_data.get("texts") or []
        if not texts:
            return {"error": "texts is required and must be non-empty"}

        inputs = self.processor(
            text=texts, return_tensors="pt", padding=True, truncation=True
        ).to(self.device)
        with self.torch.no_grad():
            feats = self._as_embeddings(
                self.model.get_text_features(**inputs), self.model.text_projection
            )
        feats = feats / feats.norm(dim=-1, keepdim=True)

        vectors = feats.cpu().tolist()
        return {"vectors": vectors, "count": len(vectors), "dim": len(vectors[0])}
