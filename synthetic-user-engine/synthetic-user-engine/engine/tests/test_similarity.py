from sue.similarity import similarity, task_words

TASK = ("You manage your team's cloud spending. Create a fixed monthly budget of $1,000 for the Atlas project. "
        "Include all Atlas project costs and exclude costs from other projects. Configure an email alert for when "
        "the project's actual spending during the month exceeds 80% of the budget. Only the Atlas project owner "
        "should receive this alert.")


def el(text):
    return {"original": text, "harness": False}


def test_words_shared_with_the_task_make_an_element_alike(vocab):
    task = task_words(TASK)
    v = vocab("full")
    assert similarity(el("Budgets & caps"), v, task) >= 1  # budget
    assert similarity(el("Cost table"), v, task) == 1  # costs
    assert similarity(el("Email alerts to project owners"), v, task) >= 3  # email, alert, project, owner
    assert similarity(el("Reports"), v, task) == 0


def test_fake_words_never_count(vocab):
    task = task_words(TASK)
    assert similarity(el("Budgets & caps"), vocab("blank"), task) == 0  # he cannot read it
    assert similarity(el("Atlas atlas-demo"), vocab("blank"), task) >= 1  # names are data, readable to all


def test_the_numbers_the_task_names():
    from sue.similarity import number, task_values
    assert task_values(TASK) == {"1000", "80"}
    assert number("$1,000") == "1000" and number("80%") == "80" and number("") is None
