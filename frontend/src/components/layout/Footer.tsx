import { Link } from "react-router-dom";

export const Footer = () => {
  return (
    <footer className="relative overflow-hidden px-4 pb-10 pt-6 sm:px-6 sm:pb-14">
      <div className="container mx-auto max-w-6xl">
        <div className="surface-card shadow-card rounded-[2rem] p-8 sm:p-10">
          <div className="grid gap-10 lg:grid-cols-[1.3fr_0.7fr_0.7fr]">
            <div className="space-y-5">
              <Link to="/" className="flex items-center gap-3">
                <div className="gradient-primary flex h-12 w-12 items-center justify-center rounded-2xl text-lg font-extrabold text-primary-foreground shadow-soft">
                  E
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                    EGR
                  </div>
                  <div className="text-xl font-semibold text-foreground">
                    Реестр компаний Беларуси
                  </div>
                </div>
              </Link>

              <p className="max-w-xl text-sm leading-7 text-muted-foreground sm:text-base">
                Аккуратный и быстрый интерфейс для поиска компаний, проверки карточек
                и работы со справочниками ЕГР без перегруженного визуального шума.
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
                <Link to="/references" className="hover:text-primary">
                  Справочники
                </Link>
              </div>
            </div>

            <div className="space-y-4">
              <div className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Фокус
              </div>
              <div className="space-y-3 text-sm text-muted-foreground">
                <div>Быстрый поиск по УНП и названию</div>
                <div>Карточка компании и связанные данные</div>
                <div>Чистый минималистичный интерфейс</div>
              </div>
            </div>
          </div>

          <div className="section-divider my-8" />

          <div className="flex flex-col gap-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <p>© {new Date().getFullYear()} EGR Service. Все права защищены.</p>
            <p>Сделано с акцентом на скорость, читаемость и спокойный визуальный ритм.</p>
          </div>
        </div>
      </div>
    </footer>
  );
};
