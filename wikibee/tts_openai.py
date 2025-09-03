from __future__ import annotations

from typing import Any, Optional

# Allow tests to monkeypatch `OpenAI` at module level without requiring the
# real `openai` package to be installed at import time. If the import fails
# we'll set OpenAI to None and import inside the constructor.
OpenAI: Any = None
try:
    from openai import OpenAI as _OpenAI

    OpenAI = _OpenAI
except Exception:  # pragma: no cover - import-time fallback
    OpenAI = None


class TTSClientError(RuntimeError):
    pass


class TTSOpenAIClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8880/v1",
        api_key: str = "not-needed",
    ):
        # Store connection parameters and defer constructing the real
        # OpenAI client until synthesis time. This lets tests monkeypatch
        # `OpenAI` to simulate failures that occur during client creation.
        self._base_url = base_url
        self._api_key = api_key
        self.client: Any = None

    def synthesize_to_file(
        self,
        text: str,
        dest_path: str,
        base_dir: str = ".",
        model: str = "kokoro",
        voice: Optional[str] = None,
        file_format: str = "mp3",
        timeout: int = 60,
    ) -> str:
        """Synthesize `text` using the OpenAI-compatible
        `audio.speech.with_streaming_response.create` API.

        Streams the response to `dest_path` (relative to base_dir). Returns
        the saved file path.
        """
        try:
            # Lazily create the OpenAI client if needed.
            global OpenAI
            if self.client is None:
                if OpenAI is None:
                    try:
                        from openai import OpenAI as _OpenAI

                        OpenAI = _OpenAI
                    except Exception as e:  # pragma: no cover - tests monkeypatch
                        raise TTSClientError(
                            "OpenAI client is not available; install 'openai' or "
                            "monkeypatch OpenAI in tests"
                        ) from e
                try:
                    self.client = OpenAI(base_url=self._base_url, api_key=self._api_key)
                except Exception as e:
                    raise TTSClientError(e)

            create_kwargs = {"model": model, "input": text, "timeout": timeout}
            if voice is not None:
                create_kwargs["voice"] = voice

            with self.client.audio.speech.with_streaming_response.create(
                **create_kwargs
            ) as response:
                # response.stream_to_file expects a path like 'output.mp3'
                # Use the provided helper to stream to a file. The OpenAI client
                # provides response.stream_to_file which writes the result to disk.
                response.stream_to_file(dest_path)

            # If stream_to_file wrote directly, return dest_path
            return dest_path
        except Exception as e:
            raise TTSClientError(e)
