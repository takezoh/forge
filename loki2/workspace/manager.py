from __future__ import annotations

import asyncio
from pathlib import Path

from loki2.clients import git


class WorkspaceManager:
    def __init__(self, worktree_dir: Path):
        self._worktree_dir = worktree_dir
        self._worktree_dir.mkdir(parents=True, exist_ok=True)

    def worktree_path(self, identifier: str) -> Path:
        return self._worktree_dir / identifier

    async def create_detached(self, repo_path: str, identifier: str, base_branch: str) -> Path:
        wt_path = self.worktree_path(identifier)
        if wt_path.exists():
            await self.destroy(repo_path, identifier)
        result = await asyncio.to_thread(
            git.worktree_add, repo_path, str(wt_path), base_branch, detach=True)
        if result.returncode != 0:
            raise RuntimeError(f"worktree_add failed: {result.stderr}")
        return wt_path

    async def create_branch(self, repo_path: str, identifier: str,
                            base_branch: str, new_branch: str) -> Path:
        wt_path = self.worktree_path(identifier)
        if wt_path.exists():
            await self.destroy(repo_path, identifier)

        if await asyncio.to_thread(git.branch_exists, repo_path, new_branch):
            result = await asyncio.to_thread(
                git.worktree_add, repo_path, str(wt_path), new_branch)
        else:
            result = await asyncio.to_thread(
                git.worktree_add, repo_path, str(wt_path), base_branch,
                new_branch=new_branch)
        if result.returncode != 0:
            raise RuntimeError(f"worktree_add failed: {result.stderr}")
        return wt_path

    async def destroy(self, repo_path: str, identifier: str):
        wt_path = self.worktree_path(identifier)
        if wt_path.exists():
            await asyncio.to_thread(git.worktree_remove, repo_path, str(wt_path))

    async def merge_to_parent(self, repo_path: str, child_branch: str,
                              parent_identifier: str, parent_branch: str) -> bool:
        wt_path = self.worktree_path(parent_identifier)
        if not wt_path.exists():
            await self.create_branch(repo_path, parent_identifier,
                                     await asyncio.to_thread(git.detect_default_branch, repo_path),
                                     parent_branch)

        message = f"Merge {child_branch} into {parent_branch}"
        result = await asyncio.to_thread(git.merge, str(wt_path), child_branch, message)
        if result.returncode != 0:
            await asyncio.to_thread(git.merge_abort, str(wt_path))
            return False
        return True
