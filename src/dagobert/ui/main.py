"""Streamlit entry point, started by `dagobert app`."""

from __future__ import annotations

# A spawned worker of the explorer's process pool imports the main script as `__mp_main__`.
# It must not draw the page, and without the imports it starts faster and logs no warnings.
if __name__ == "__main__":
    import os
    from collections.abc import Callable
    from pathlib import Path

    import streamlit as st

    from dagobert import datadir, i18n
    from dagobert.i18n import N_, _, pgettext
    from dagobert.problems import InputError
    from dagobert.revisions import BusyError
    from dagobert.runner import DATA_ENV
    from dagobert.schema import SchemaError
    from dagobert.store import assets_file, streams_file
    from dagobert.ui import (
        BOOT,
        CAME,
        PAGE,
        PAGE_STYLE,
        PAGES,
        arrived,
        assets,
        assumptions,
        cashflows,
        data,
        explorer,
        features,
        flows,
        is_mobile,
        language,
        language_switch,
        mode,
        overview,
        scenarios,
        session_seen,
        sliders,
        snapshot,
        spend,
        told,
        transfer,
        welcome,
    )

    session_seen.set()
    # first: every text of the run takes the language of the session (a callback runs before)
    i18n.activate(lang := language())
    DATA = Path(os.environ.get(DATA_ENV, "data"))

    st.set_page_config(
        page_title="Dagobert",
        layout="wide",
        initial_sidebar_state="collapsed" if is_mobile() else "auto",
    )
    st.html(PAGE_STYLE)
    # A tab from before a server restart reconnects with stale scripts and widget state.
    # The address bar of Chrome on a phone takes the page background. Its media query follows
    # the OS, not a theme picked in the menu; the app follows the OS by default. Only `.stApp`
    # knows the theme of the menu: the page takes its color scheme, so a dialog, which draws
    # outside it, follows the theme too. The page takes the language of the session: hyphens,
    # screen readers and the translate offer of Chrome read it. Streamlit runs the script again
    # when its text changes (another language, a new boot), so it declares in a block: a second
    # `const` in the global scope of the page throws before the first line.
    st.html(
        f"""<script>{{
        document.documentElement.lang = "{lang}";
        const last = sessionStorage.getItem("dagobert-boot");
        sessionStorage.setItem("dagobert-boot", "{BOOT}");
        if (last && last !== "{BOOT}") location.reload();
        if (!document.querySelector("meta[name=theme-color]"))
          for (const [scheme, color] of [["light", "#ffffff"], ["dark", "#0e1117"]])
            document.head.append(Object.assign(document.createElement("meta"), {{
              name: "theme-color", media: "(prefers-color-scheme: " + scheme + ")", content: color
            }}));
        const app = document.querySelector(".stApp");
        const follow = () => {{
          document.documentElement.style.colorScheme = getComputedStyle(app).colorScheme;
        }};
        if (app && !app.dataset.dgScheme) {{
          app.dataset.dgScheme = "1";
          follow();
          new MutationObserver(follow).observe(app, {{attributeFilter: ["class"]}});
        }}
        }}</script>""",
        unsafe_allow_javascript=True,
    )
    # An empty or missing data directory shows the first-run page without the navigation. The
    # pages stay registered, so the start can go to the Overview or the Assumptions page. The
    # navigation registers the pages that the mode, the features and the inputs show
    # (`mode.pages`), all of them for inputs that do not parse, so the error screen below keeps
    # the page that fixes them.
    first_run = datadir.empty(DATA)
    shown = mode.pages(
        mode.Uses() if first_run else mode.uses(DATA), mode.features_off(DATA), mode.advanced()
    )

    def entry(
        title: str, run: Callable[[], None], url_path: str | None = None
    ) -> tuple[str, st.Page]:
        """A page by its title in English, which names it in links (`ui.page_link`) and in the
        revision log (`ui.source`) whatever words it shows. The Overview, without a path, is the
        default."""
        return title, st.Page(run, title=_(title), url_path=url_path, default=url_path is None)

    sections = {
        _("Track"): dict(
            [
                entry(N_("Overview"), lambda: overview.page(streams_file(DATA))),
                entry(N_("Snapshot"), lambda: snapshot.page(assets_file(DATA)), "snapshot"),
                entry(N_("Assets"), lambda: assets.page(assets_file(DATA)), "assets"),
                entry(N_("Cashflows"), lambda: cashflows.page(streams_file(DATA)), "cashflows"),
                entry(N_("Spend"), lambda: spend.page(streams_file(DATA)), "spend"),
            ]
        ),
        pgettext("navigation", "Plan"): dict(
            [
                entry(N_("Explorer"), lambda: explorer.page(DATA), "explorer"),
                entry(N_("Flows"), lambda: flows.page(DATA), "flows"),
            ]
        ),
        _("Setup"): dict(
            [
                entry(N_("Features"), lambda: features.page(DATA), "features"),
                entry(N_("Data"), lambda: data.page(DATA), "data"),
                entry(N_("Assumptions"), lambda: assumptions.page(DATA), "assumptions"),
                entry(N_("Scenarios"), lambda: scenarios.page(DATA), "scenarios"),
                entry(N_("Export and import"), lambda: transfer.page(DATA), "transfer"),
            ]
        ),
    }
    page = st.navigation(
        {
            section: [p for title, p in pages.items() if title in shown]
            for section, pages in sections.items()
        },
        position="hidden" if first_run else "sidebar",
    )
    # Every run brings the data directory to the current schema first and records the edits
    # outside the app, at the cost of a glob and a read of the inputs. Inputs that do not load
    # show their problems instead of a traceback. The title of the page names its writes, and
    # a link to another page takes the page registered here (`ui.page_link`; a page that the
    # navigation leaves out is None, so no link goes there). The mode and the language switch
    # end the sidebar, below the controls of a page, also beside a problem. The toasts of a save
    # of the run before show first, whichever page it went to.
    pages = {
        title: p if title in shown else None
        for section in sections.values()
        for title, p in section.items()
    }
    st.session_state[CAME] = st.session_state.get(PAGE)
    st.session_state[PAGE] = next(title for title, p in pages.items() if p is page)
    st.session_state[PAGES] = pages
    sliders.carry(arrived=arrived())  # the explorer keeps its selection across pages
    told()
    try:
        if first_run:
            welcome.page(DATA)
        else:
            datadir.open(DATA)
            page.run()
    except (InputError, SchemaError) as err:
        st.error(_("The inputs do not load:"), icon=":material/error:")
        st.code(str(err), language=None, wrap_lines=True)
    except BusyError:
        st.error(_("Another save is running: reload the page."), icon=":material/error:")
    finally:
        sliders.keep()
        mode.mode_switch()
        language_switch()
