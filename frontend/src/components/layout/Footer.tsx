import { Link } from "react-router-dom";

export const Footer = () => {
  return (
    <footer className="relative overflow-hidden px-4 pb-10 pt-6 sm:px-6 sm:pb-14">
      <div className="container mx-auto max-w-7xl">
        <div className="surface-card shadow-card rounded-[2rem] p-8 sm:p-10">
          <div className="grid gap-10 md:grid-cols-[1fr_auto] md:items-start">
            <div className="space-y-5">
              <Link to="/" className="flex items-center gap-3">
                <div className="gradient-primary flex h-12 w-12 items-center justify-center rounded-2xl text-lg font-extrabold text-primary-foreground shadow-soft">
                  T
                </div>
                <div className="text-lg font-bold uppercase tracking-[0.2em] text-foreground">
                  TENDERS.BY
                </div>
              </Link>
              <p className="max-w-xl text-sm leading-6 text-muted-foreground">
                Поиск, проверка и понятное досье компаний Беларуси в одном сервисе.
              </p>
            </div>

            <div className="space-y-4">
              <div className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Навигация
              </div>
              <div className="flex flex-col gap-3 text-sm text-foreground">
                <a href="#features" className="hover:text-primary">
                  Возможности
                </a>
                <a href="#about" className="hover:text-primary">
                  О сервисе
                </a>
                <a href="#hero-search" className="hover:text-primary">
                  Проверить компанию
                </a>
              </div>
            </div>
          </div>

          <div className="section-divider my-8" />

          <div className="flex flex-col gap-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <p>© {new Date().getFullYear()} TENDERS.BY. Все права защищены.</p>
            <p>Официальные данные · понятный интерфейс для решений</p>
          </div>
        </div>
      </div>
    </footer>
  );
};
