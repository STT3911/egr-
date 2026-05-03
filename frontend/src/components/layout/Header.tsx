import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Menu, Moon, Search, Sun, X } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { CompanySearch } from "@/components/CompanySearch";

const homeLinks = [
  { label: "Возможности", href: "#features" },
  { label: "О сервисе", href: "#about" },
];

export const Header = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const location = useLocation();
  const isHomePage = location.pathname === "/";

  useEffect(() => {
    const theme = localStorage.getItem("theme");
    const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    if (theme === "dark" || (!theme && systemPrefersDark)) {
      setIsDark(true);
      document.documentElement.classList.add("dark");
    } else {
      setIsDark(false);
      document.documentElement.classList.remove("dark");
    }
  }, []);

  useEffect(() => {
    setIsMenuOpen(false);
  }, [location.pathname]);

  const toggleTheme = () => {
    const newTheme = !isDark;
    setIsDark(newTheme);
    localStorage.setItem("theme", newTheme ? "dark" : "light");

    if (newTheme) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed inset-x-0 top-4 z-50 px-4 sm:px-6"
    >
      <div className="container mx-auto max-w-6xl">
        <div className="surface-card shadow-card rounded-[1.75rem] px-4 py-3 sm:px-5">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex min-w-0 items-center gap-3">
              <div className="gradient-primary flex h-11 w-11 items-center justify-center rounded-2xl text-lg font-extrabold text-primary-foreground shadow-soft">
                E
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                  EGR
                </div>
                <div className="truncate text-base font-semibold text-foreground max-[560px]:hidden">
                  Реестр компаний Беларуси
                </div>
              </div>
            </Link>

            {isHomePage ? (
              <nav className="ml-4 hidden items-center gap-2 lg:flex">
                {homeLinks.map((link) =>
                  link.href.startsWith("/") ? (
                    <Link
                      key={link.label}
                      to={link.href}
                      className="rounded-full px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  ) : (
                    <a
                      key={link.label}
                      href={link.href}
                      className="rounded-full px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
                    >
                      {link.label}
                    </a>
                  ),
                )}
              </nav>
            ) : (
              <div className="mx-2 hidden flex-1 lg:block">
                <CompanySearch
                  variant="compact"
                  placeholder="Поиск по УНП или названию компании"
                />
              </div>
            )}

            <div className="ml-auto flex items-center gap-2">
              {isHomePage && (
                <a
                  href="#hero-search"
                  className="hidden items-center gap-2 rounded-full border border-border/80 bg-card/72 px-4 py-2 text-sm font-semibold text-foreground hover:-translate-y-0.5 hover:shadow-soft md:inline-flex"
                >
                  <Search className="h-4 w-4 text-primary" />
                  Найти компанию
                </a>
              )}

              <button
                onClick={toggleTheme}
                className="glass flex h-11 w-11 items-center justify-center rounded-2xl hover:-translate-y-0.5 hover:shadow-soft"
                aria-label="Переключить тему"
              >
                {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
              </button>

              <button
                className="glass flex h-11 w-11 items-center justify-center rounded-2xl lg:hidden"
                onClick={() => setIsMenuOpen((value) => !value)}
                aria-label="Открыть меню"
              >
                {isMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            </div>
          </div>

          {isMenuOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="surface-divider mt-4 space-y-4 pt-4 lg:hidden"
            >
              {isHomePage ? (
                <div className="flex flex-col gap-2">
                  {homeLinks.map((link) =>
                    link.href.startsWith("/") ? (
                      <Link
                        key={link.label}
                        to={link.href}
                        className="rounded-2xl px-4 py-3 text-sm font-medium text-foreground hover:bg-foreground/5"
                      >
                        {link.label}
                      </Link>
                    ) : (
                      <a
                        key={link.label}
                        href={link.href}
                        className="rounded-2xl px-4 py-3 text-sm font-medium text-foreground hover:bg-foreground/5"
                      >
                        {link.label}
                      </a>
                    ),
                  )}
                  <a
                    href="#hero-search"
                    className="gradient-primary rounded-2xl px-4 py-3 text-sm font-semibold text-primary-foreground shadow-soft"
                  >
                    Найти компанию
                  </a>
                </div>
              ) : (
                <CompanySearch
                  variant="compact"
                  placeholder="Поиск по УНП или названию компании"
                  onSearchStart={() => setIsMenuOpen(false)}
                />
              )}
            </motion.div>
          )}
        </div>
      </div>
    </motion.header>
  );
};
