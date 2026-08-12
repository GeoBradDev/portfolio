/*=========================================================================

  Site behavior for GeoBrad.dev.

  Loaded by index.html only. resume.html and privacy.html are standalone.

  Every block below has a matching element in index.html. Adding code here
  that targets an element the markup does not contain recreates issue #16,
  where 664 lines sat dead in the tree for two years.

=========================================================================*/

$(function () {
    "use strict";

    var allWindow = $(window),
        navBar = $(".nav-wrapper"),
        scrollUp = $(".scroll-up"),
        navList = navBar.find("ul.navbar-nav"),
        sections = $(".one-page-section"),
        skillsSection = $(".skills-section"),
        skillLines = $(".progress-bar-line"),
        motionQuery = window.matchMedia
            ? window.matchMedia("(prefers-reduced-motion: reduce)")
            : null,
        scrollPos = 0;

    // The navbar is position: fixed, so anything that scrolls to a section
    // has to clear it or the heading lands underneath.
    //
    // Below the Bootstrap breakpoint an open dropdown is in flow inside the
    // fixed header, which measures 278px against the 63px it collapses back
    // to. Since every caller here is about to close that menu, subtract it.
    function navHeight() {
        var collapse = navBar.find(".navbar-collapse"),
            height = navBar.outerHeight() || 0;

        if (collapse.hasClass("in")) {
            height -= collapse.outerHeight() || 0;
        }

        return height;
    }

    // Honor the OS setting rather than animating over someone who asked us
    // not to. Read at call time, not at load, since the setting can change.
    function duration(speed) {
        return motionQuery && motionQuery.matches ? 0 : speed;
    }

/*------------------------------------------------
  Preloader
--------------------------------------------------*/

    allWindow.on("load", function () {
        $(".loader-con").fadeOut("slow");
    });

/*------------------------------------------------
  Sticky navigation and scroll-to-top visibility
--------------------------------------------------*/

    function stickyNav() {
        navBar.toggleClass("nav-sticky", scrollPos >= 100);
        scrollUp.toggleClass("show-up-btn", scrollPos >= 1000);
    }

/*------------------------------------------------
  Smooth scrolling for on-page anchors
--------------------------------------------------*/

    $("a.scroll").on("click", function (event) {
        if (location.pathname.replace(/^\//, "") !== this.pathname.replace(/^\//, "") ||
            location.hostname !== this.hostname) {
            return;
        }

        var target = $(this.hash);
        if (!target.length) {
            target = $("[name=" + this.hash.slice(1) + "]");
        }
        if (!target.length) {
            return;
        }

        event.preventDefault();
        $("html, body").animate({
            scrollTop: Math.max(0, target.offset().top - navHeight())
        }, duration($(this).data("speed") || 800));
    });

    scrollUp.on("click", function (event) {
        event.preventDefault();
        $("html, body").animate({ scrollTop: 0 }, duration(900));
    });

/*------------------------------------------------
  Close the mobile dropdown after tapping a link
--------------------------------------------------*/

    // Bootstrap 3 returns early from hide() when the element lacks .in, so
    // this is a no-op on desktop where CSS keeps the menu expanded.
    navBar.find(".navbar-collapse a").on("click", function () {
        navBar.find(".navbar-collapse").collapse("hide");
    });

/*------------------------------------------------
  Highlight the nav link for the visible section
--------------------------------------------------*/

    function changeActiveNavLink() {
        var probe = scrollPos + navHeight();

        sections.each(function () {
            var section = $(this),
                sectionTop = section.offset().top;

            if (probe < sectionTop || probe > sectionTop + section.height()) {
                return;
            }

            navList.find("a").removeClass("active");
            navList.find('[href="#' + section.attr("id") + '"]').addClass("active");
        });
    }

/*------------------------------------------------
  Skill bars, animated once when scrolled into view
--------------------------------------------------*/

    function progressBars() {
        if (!skillsSection.length || skillsSection.hasClass("done")) {
            return;
        }

        var trigger = skillsSection.offset().top - (allWindow.height() - 160);
        if (scrollPos < trigger) {
            return;
        }

        skillsSection.addClass("done");
        skillLines.each(function () {
            var line = $(this),
                percent = parseInt(line.attr("data-percent"), 10);

            if (!isNaN(percent)) {
                line.css("width", percent + "%");
            }
        });
    }

/*------------------------------------------------
  One scroll handler drives all three
--------------------------------------------------*/

    function scrollFunctions() {
        scrollPos = allWindow.scrollTop();
        stickyNav();
        changeActiveNavLink();
        progressBars();
    }

    // One pass per frame. The three functions above interleave class writes
    // with about a dozen offset and height reads, and native scrolling fires
    // far more often than once a frame now that the old wheel-event hijack is
    // gone, so running them unthrottled thrashes layout on every event.
    var pending = false;

    allWindow.on("scroll", function () {
        if (pending) {
            return;
        }
        pending = true;
        window.requestAnimationFrame(function () {
            pending = false;
            scrollFunctions();
        });
    });

    // Run once so a reload partway down the page, or a deep link, starts in
    // the right state instead of waiting for the first scroll event.
    scrollFunctions();

});
