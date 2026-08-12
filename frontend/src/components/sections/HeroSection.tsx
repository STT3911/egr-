import { motion } from "framer-motion";
import { ArrowDownRight, Database, Gauge, Layers3, Sparkles } from "lucide-react";
import { CompanySearch } from "@/components/CompanySearch";
import { AnimatedHeroBackdrop } from "./AnimatedHeroBackdrop";
import { DataCube } from "./DataCube";

const proof = [
  { icon: Database, value: "1,6 млн", label: "компаний в базе" },
  { icon: Layers3, value: "Одно окно", label: "вместо десятков вкладок" },
  { icon: Gauge, value: "120 мс", label: "средний отклик" },
];

const sourceLabels = ["Регистрационные данные", "Банкротства", "Лицензии", "Проверки", "Связанные компании", "История названий"];

export const HeroSection = () => {
  return (
    <section className="hero-shell relative overflow-hidden px-4 pb-12 pt-28 sm:px-6 sm:pb-16 sm:pt-36">
      <AnimatedHeroBackdrop />

      <div className="container relative z-10 mx-auto max-w-7xl">
        <div className="hero-layout">
          <div className="hero-copy max-w-3xl lg:pb-6">
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              className="eyebrow mb-6"
            >
              <Sparkles className="h-4 w-4 text-accent" />
              Платформа бизнес-разведки TENDERS.BY
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 26 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05 }}
              className="max-w-4xl text-4xl font-extrabold leading-[0.94] text-foreground sm:text-5xl md:text-6xl xl:text-[4.5rem]"
            >
              Проверяйте бизнес
              <span className="block text-gradient">до сделки</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 26 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.12 }}
              className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8"
            >
              Одно досье вместо десятков вкладок: официальные данные, владельцы,
              связи, события и сигналы риска по компаниям Беларуси.
            </motion.p>

            <motion.div
              id="hero-search"
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.2 }}
              className="mt-8 scroll-mt-28"
            >
              <CompanySearch
                variant="hero"
                placeholder="УНП или название компании"
              />
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="mt-5 flex flex-wrap items-center gap-4 text-sm text-muted-foreground"
            >
              <a
                href="#features"
                className="group inline-flex items-center gap-2 font-semibold text-foreground"
              >
                Посмотреть возможности
                <ArrowDownRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5 group-hover:translate-y-0.5" />
              </a>
              <span className="h-1 w-1 rounded-full bg-border" />
              <span>Открытый поиск по официальным данным</span>
            </motion.div>

          </div>

          <motion.div
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, delay: 0.16 }}
            className="hero-cube-wrap relative min-w-0"
          >
            <DataCube />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.38 }}
            className="hero-proof-grid grid gap-3 sm:grid-cols-3"
          >
            {proof.map((item) => (
              <div key={item.label} className="hero-proof-item">
                <div className="hero-proof-icon">
                  <item.icon className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-lg font-bold text-foreground">{item.value}</div>
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                </div>
              </div>
            ))}
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.52 }}
          className="source-rail"
          aria-label="Данные сервиса"
        >
          <div className="source-rail-label">В одном профиле</div>
          <div className="source-rail-track">
            {[...sourceLabels, ...sourceLabels].map((label, index) => (
              <span key={`${label}-${index}`}>
                <span className="source-rail-dot" />
                {label}
              </span>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
};
