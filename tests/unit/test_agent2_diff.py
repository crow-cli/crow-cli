from crow_cli.agent2.tools import diff_content


def test_add_patch_marks_absent_before_side():
    diff = diff_content("hello.txt", "/workspace", "hello, world!", None)
    assert diff.changes[0].operation == "add"
    assert diff.changes[0].path == "/workspace/hello.txt"
    assert "--- /dev/null\n" in diff.patch.text
    assert "+hello, world!\n\\ No newline at end of file\n" in diff.patch.text


def test_modify_without_trailing_newlines_has_separate_patch_lines():
    diff = diff_content("hello.txt", "/workspace", "goodbye, world!", "hello, world!")
    assert diff.changes[0].operation == "modify"
    assert "-hello, world!\n\\ No newline at end of file\n+goodbye, world!\n" in diff.patch.text


def test_empty_existing_file_is_a_modification():
    assert diff_content("hello.txt", "/workspace", "hello\n", "").changes[0].operation == "modify"
