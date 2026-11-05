/*=========================================================================

  Site behavior for GeoBrad.dev.

  Loaded by index.html only. resume.html and privacy.html are standalone.

  Every block below has a matching element in index.html. Adding code here
  that targets an element the markup does not contain recreates issue #16,
  where 664 lines sat dead in the tree for two years.

  No library. Issue #31 deleted js/jquery.min.js and js/bootstrap.min.js,
  127 KB loaded to run the few dozen lines below.

  Smooth scrolling is the browser's. css/style.css sets scroll-behavior:
  smooth on html.smooth-scroll, only when the visitor has not asked for
  reduced motion, and a scroll-margin-top on every section so a fragment
  lands below the fixed header. The one part that lives here is adding the
  smooth-scroll class, a frame after load (see onLoad below), so a deep
  link's first jump is instant. Nothing here may cancel a nav link's click
  or scroll the page itself, or it fights that and loses the hash update.
  Focus is the browser's too: every section is tabindex="-1", and native
  fragment navigation focuses a focusable target, so nothing here moves it.

=========================================================================*/

(function () {
    "use strict";

    function init() {
        var navBar = document.querySelector(".nav-wrapper"),
            scrollUp = document.querySelector(".scroll-up"),
            toggle = document.querySelector(".navbar-toggle"),
            menu = toggle ? document.getElementById(toggle.getAttribute("aria-controls")) : null,
            navLinks = navBar ? navBar.querySelectorAll("ul.navbar-nav a") : [],
            sections = document.querySelectorAll(".one-page-section"),
            skillsSection = document.querySelector(".skills-section"),
            skillLines = document.querySelectorAll(".progress-bar-line"),
            motionQuery = window.matchMedia
                ? window.matchMedia("(prefers-reduced-motion: reduce)")
                : null,
            scrollPos = 0;

        function isOpen() {
            return !!toggle && toggle.getAttribute("aria-expanded") === "true";
        }

        // True below the 768px breakpoint, where CSS shows the toggle.
        function toggleShown() {
            return !!toggle && window.getComputedStyle(toggle).display !== "none";
        }

        // The header is position: fixed. Below the 768px breakpoint an open
        // menu is in flow inside it, which measures 278px against the 63px
        // it collapses back to, so the active-link probe below subtracts the
        // open menu rather than reading the header raw. Above it the links
        // sit inline and are part of the header's real height, even if the
        // menu was left open before a resize.
        function navHeight() {
            var height = navBar ? navBar.offsetHeight : 0;

            if (menu && isOpen() && toggleShown()) {
                height -= menu.offsetHeight;
            }

            return height;
        }

        function pageTop(element) {
            return element.getBoundingClientRect().top + window.pageYOffset;
        }

/*------------------------------------------------
  Preloader
--------------------------------------------------*/

        // Fades over 600ms, the "slow" the old fadeOut call used, then
        // leaves the layout. transitionend does not fire if the fade never runs, for
        // instance because the portfolio renderer already hid the loader, so
        // a timeout finishes the job either way and the page can never stay
        // covered.
        function hideLoader() {
            var loader = document.querySelector(".loader-con"),
                done = false;

            if (!loader) {
                return;
            }

            function finish() {
                if (done) {
                    return;
                }
                done = true;
                loader.style.display = "none";
            }

            loader.addEventListener("transitionend", function (event) {
                if (event.target === loader) {
                    finish();
                }
            });
            window.setTimeout(finish, 700);
            loader.style.transition = "opacity 600ms ease-in-out";
            void loader.offsetWidth;
            loader.style.opacity = "0";
        }

        // Smooth scrolling starts here, a frame after load, and not from
        // the first paint: see html.smooth-scroll in css/style.css. Until
        // then a deep link's jump is instant and lands against the final
        // layout.
        function onLoad() {
            hideLoader();
            window.requestAnimationFrame(function () {
                document.documentElement.classList.add("smooth-scroll");
            });
        }

        if (document.readyState === "complete") {
            onLoad();
        } else {
            window.addEventListener("load", onLoad);
        }

/*------------------------------------------------
  Mobile menu toggle
--------------------------------------------------*/

        // A plain button that owns its state. aria-expanded is the single
        // source of truth: CSS shows the menu from .is-open, and the 350ms
        // height animation is the one Bootstrap's collapse plugin ran.
        // .is-collapsing exists only while that animation runs.
        var pendingFinish = null;

        function animates() {
            return toggleShown() && !(motionQuery && motionQuery.matches);
        }

        function setMenu(open) {
            if (!toggle || !menu || open === isOpen()) {
                return;
            }

            toggle.setAttribute("aria-expanded", open ? "true" : "false");

            if (pendingFinish) {
                pendingFinish();
            }

            if (!animates()) {
                menu.classList.toggle("is-open", open);
                return;
            }

            var finished = false;

            // The links inside transition their color on .nav-sticky, and
            // their transitionend bubbles up here. Only the menu's own
            // height ends the animation.
            function onEnd(event) {
                if (event.target === menu && event.propertyName === "height") {
                    finish();
                }
            }

            function finish() {
                if (finished) {
                    return;
                }
                finished = true;
                pendingFinish = null;
                menu.removeEventListener("transitionend", onEnd);
                menu.classList.remove("is-collapsing");
                menu.classList.toggle("is-open", open);
                menu.style.height = "";
            }

            if (open) {
                menu.classList.add("is-open");
                menu.style.height = "0px";
                menu.classList.add("is-collapsing");
                void menu.offsetHeight;
                menu.style.height = menu.scrollHeight + "px";
            } else {
                menu.style.height = menu.offsetHeight + "px";
                void menu.offsetHeight;
                menu.classList.add("is-collapsing");
                menu.style.height = "0px";
            }

            pendingFinish = finish;
            menu.addEventListener("transitionend", onEnd);
            window.setTimeout(finish, 400);
        }

        if (toggle && menu) {
            toggle.addEventListener("click", function () {
                setMenu(!isOpen());
            });

            // Closing runs in the click handler, before the browser performs
            // the fragment navigation, and does not cancel it.
            menu.addEventListener("click", function (event) {
                if (event.target.closest("a")) {
                    setMenu(false);
                }
            });
        }

/*------------------------------------------------
  Sticky navigation and scroll-to-top visibility
--------------------------------------------------*/

        function stickyNav() {
            if (navBar) {
                navBar.classList.toggle("nav-sticky", scrollPos >= 100);
            }
            if (scrollUp) {
                scrollUp.classList.toggle("show-up-btn", scrollPos >= 1000);
            }
        }

/*------------------------------------------------
  Highlight the nav link for the visible section
--------------------------------------------------*/

        // The section's extent is its border box. The old version used
        // the content box, which left each section's bottom padding as a
        // band where no link matched and the previous one stayed lit.
        //
        // The extra pixel: section tops are fractional and scroll offsets
        // are whole, so a nav link can land its section up to a pixel short
        // of the header, which would leave the previous section's link lit.
        function changeActiveNavLink() {
            var probe = scrollPos + navHeight() + 1;

            Array.prototype.forEach.call(sections, function (section) {
                var sectionTop = pageTop(section);

                if (probe < sectionTop || probe > sectionTop + section.offsetHeight) {
                    return;
                }

                Array.prototype.forEach.call(navLinks, function (link) {
                    link.classList.toggle("active", link.getAttribute("href") === "#" + section.id);
                });
            });
        }

/*------------------------------------------------
  Skill bars, animated once when scrolled into view
--------------------------------------------------*/

        function progressBars() {
            if (!skillsSection || skillsSection.classList.contains("done")) {
                return;
            }

            var trigger = pageTop(skillsSection) - (document.documentElement.clientHeight - 160);
            if (scrollPos < trigger) {
                return;
            }

            skillsSection.classList.add("done");
            Array.prototype.forEach.call(skillLines, function (line) {
                var percent = parseInt(line.getAttribute("data-percent"), 10);

                if (!isNaN(percent)) {
                    line.style.width = percent + "%";
                }
            });
        }

/*------------------------------------------------
  One scroll handler drives all three
--------------------------------------------------*/

        function scrollFunctions() {
            scrollPos = window.pageYOffset;
            stickyNav();
            changeActiveNavLink();
            progressBars();
        }

        // One pass per frame. The three functions above interleave class
        // writes with about a dozen layout reads, and scroll fires far more
        // often than once a frame, so running them unthrottled thrashes
        // layout on every event. Resize shares the throttle: a rotate moves
        // every section, and the state used to wait for the next scroll.
        var pending = false;

        function schedule() {
            if (pending) {
                return;
            }
            pending = true;
            window.requestAnimationFrame(function () {
                pending = false;
                scrollFunctions();
            });
        }

        window.addEventListener("scroll", schedule, { passive: true });
        window.addEventListener("resize", schedule);

        // Run once so a reload partway down the page, or a deep link, starts
        // in the right state instead of waiting for the first scroll event.
        scrollFunctions();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
