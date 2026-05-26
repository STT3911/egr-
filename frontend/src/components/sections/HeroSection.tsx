import { motion } from "framer-motion";
import { Building2, Search, ShieldCheck, Sparkles } from "lucide-react";
import { CompanySearch } from "@/components/CompanySearch";
import { AnimatedCounter } from "@/components/AnimatedCounter";
import { AnimatedHeroBackdrop } from "./AnimatedHeroBackdrop";

const proof = [
  { label: "Компаний", value: 1.6, suffix: "M+", decimals: 1 },
  { label: "Справочников", value: 20, suffix: "+" },
  { label: "Отклик", value: 120, suffix: "ms" },
];

const previewRows = [
  {
    title: "Карточка компании",
    caption: "Статус, адрес, история названий и регистрационные данные",
    icon: Building2,
  },
  {
    title: "Поиск по ЕГР",
    caption: "Подсказки по УНП, текущему и историческому названию",
    icon: Search,
  },
  {
    title: "Контроль выдачи",
    caption: "Синхронизация данных и аккуратная, понятная структура ответа",
    icon: ShieldCheck,
  },
];

const iconBadgeClass =
  "flex h-10 w-10 items-center justify-center rounded-2xl border border-border/80 bg-background/60 text-primary shadow-[inset_0_1px_0_hsl(var(--card)/0.8)]";

export const HeroSection = () => {
  return (
    <section className="gradient-hero relative overflow-hidden px-4 pb-14 pt-28 sm:px-6 sm:pb-20 sm:pt-36">
      <AnimatedHeroBackdrop />

      <div className="container relative z-10 mx-auto max-w-6xl">
        <div className="grid items-center gap-8 lg:grid-cols-[1.02fr_0.98fr] lg:gap-12">
          <div className="max-w-3xl">
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="eyebrow mb-6"
            >
              <Sparkles className="h-4 w-4 text-accent" />
              Поиск компаний по данным ЕГР Беларуси
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 26 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05 }}
              className="max-w-4xl text-4xl font-extrabold leading-[0.95] text-foreground sm:text-5xl md:text-6xl xl:text-7xl"
            >
              Всё о компаниях Беларуси
              <span className="block text-gradient">в одном сервисе</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 26 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.12 }}
              className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8"
            >
              Ищите организации и ИП по УНП, открывайте полную карточку компании,
              проверяйте статусы, адреса, историю названий и связанные данные без
              перегруженных экранов и лишних переходов.
            </motion.p>

            <motion.div
              id="hero-search"
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.2 }}
              className="mt-7 scroll-mt-28"
            >
              <CompanySearch
                variant="hero"
                placeholder="Введите УНП или название компании"
              />
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.28 }}
              className="mt-4 flex flex-wrap items-center gap-3 text-sm text-muted-foreground"
            >
              <div className="glass rounded-full px-4 py-2">Поиск по УНП, названию и истории</div>
              <div className="glass rounded-full px-4 py-2">Карточки компаний и справочники ЕГР</div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.34 }}
              className="mt-8 flex flex-wrap gap-3"
            >
              <a
                href="#features"
                className="glass inline-flex items-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold text-foreground hover:-translate-y-0.5 hover:shadow-soft"
              >
                Что доступно в сервисе
              </a>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.42 }}
              className="mt-8 grid gap-3 sm:grid-cols-3"
            >
              {proof.map((item) => (
                <div key={item.label} className="surface-card rounded-[1.5rem] p-4 sm:p-5">
                  <div className="text-3xl font-extrabold text-foreground">
                    <span className="text-gradient">
                      <AnimatedCounter
                        value={item.value}
                        suffix={item.suffix}
                        decimals={item.decimals}
                      />
                    </span>
                  </div>
                  <div className="mt-1 text-sm text-muted-foreground">{item.label}</div>
                </div>
              ))}
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.18 }}
            className="relative max-[420px]:px-0"
          >
            <div className="surface-card shadow-glow relative overflow-hidden rounded-[1.8rem] p-4 sm:rounded-[2rem] sm:p-6">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/8 via-transparent to-accent/8" />
              <div className="relative">
                <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border/70 pb-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                      Live Preview
                    </div>
                    <div className="mt-1 max-w-sm text-xl font-semibold leading-tight text-foreground sm:text-2xl">
                      Быстрый доступ к данным компании
                    </div>
                  </div>
                  <div className="glass rounded-full px-3 py-2 text-xs font-semibold text-foreground">
                    ЕГР online
                  </div>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-[1.08fr_0.92fr]">
                  <div className="space-y-3">
                    {previewRows.map((row, index) => (
                      <motion.div
                        key={row.title}
                        initial={{ opacity: 0, x: -16 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.45, delay: 0.28 + index * 0.08 }}
                        className="surface-card rounded-[1.25rem] p-4"
                      >
                        <div className="flex items-start gap-3">
                          <div className={iconBadgeClass}>
                            <row.icon className="h-4.5 w-4.5" />
                          </div>
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-foreground">{row.title}</div>
                            <div className="mt-1 text-sm leading-6 text-muted-foreground">
                              {row.caption}
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>

                  <div className="space-y-3">
                    <div className="surface-card rounded-[1.25rem] p-4 sm:p-5">
                      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Доступность
                      </div>
                      <div className="mt-3 text-4xl font-extrabold text-gradient">
                        <AnimatedCounter value={99.9} suffix="%" decimals={1} />
                      </div>
                      <div className="mt-2 text-sm leading-6 text-muted-foreground">
                        Поиск, карточка компании и справочники работают как единый сценарий.
                      </div>
                    </div>

                    <div className="surface-card rounded-[1.25rem] p-4 sm:p-5">
                      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Search Index
                      </div>
                      <div className="mt-2 text-base font-semibold text-foreground">Поиск по всей базе</div>
                      <div className="mt-1 text-sm leading-6 text-muted-foreground">
                        Полнотекстовый индекс ускоряет выдачу по компаниям и историческим названиям.
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};
