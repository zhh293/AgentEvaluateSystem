class APIKeyVault:
    """API Key 暂存器——仅在内存中保存，不写入数据库或文件"""

    _store: dict[str, str] = {}

    @classmethod
    def stash(cls, submission_id: str, api_key: str):
        cls._store[submission_id] = api_key

    @classmethod
    def retrieve_and_purge(cls, submission_id: str) -> str | None:
        return cls._store.pop(submission_id, None)
