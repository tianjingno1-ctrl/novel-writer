"""infra.console 单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from infra import console


class SafePrintTests(unittest.TestCase):
    def test_safe_print_survives_unicode_encode_error(self) -> None:
        fake_stdout = MagicMock()
        fake_stdout.encoding = "gbk"
        with patch("builtins.print") as mock_print:
            mock_print.side_effect = [
                UnicodeEncodeError("gbk", "x", 0, 1, "illegal"),
                None,
            ]
            with patch.object(console, "sys") as mock_sys:
                mock_sys.stdout = fake_stdout
                console.safe_print("💾 已覆盖保存")
        self.assertEqual(mock_print.call_count, 2)


if __name__ == "__main__":
    unittest.main()
