import { motion } from "framer-motion";
import { Building2, Shield, Zap } from "lucide-react";
import { CompanySearch } from "@/components/CompanySearch";
import { AnimatedCounter } from "@/components/AnimatedCounter";
import { AnimatedHeroBackdrop } from "./AnimatedHeroBackdrop";

export const HeroSection = () => {

  return (
    <section className="relative min-h-screen flex items-center justify-center gradient-hero overflow-hidden pt-20">
      <AnimatedHeroBackdrop />

      <div className="container mx-auto px-4 sm:px-6 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass shadow-soft mb-8"
          >
            <motion.span
              animate={{ rotate: [0, 8, -8, 0], scale: [1, 1.12, 1] }}
              transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
              className="flex"
            >
              <Zap className="w-4 h-4 text-primary" />
            </motion.span>
            <span className="text-sm font-medium text-foreground">Данные ЕГР в реальном времени</span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold text-foreground mb-6 leading-tight text-balance"
          >
            Вся информация о компаниях{" "}
            <span className="text-gradient">Беларуси</span>
          </motion.h1>

          {/* Subtitle */}
          <motion.p
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="text-lg sm:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto text-pretty"
          >
            Современный сервис для поиска и проверки компаний по данным Единого государственного регистра Республики Беларусь
          </motion.p>

          {/* Search Form */}
          <motion.div
            id="hero-search"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="mb-12"
          >
            <CompanySearch 
              variant="hero"
              placeholder="Введите УНП или название компании"
            />
          </motion.div>

          {/* Stats */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            className="grid grid-cols-2 sm:grid-cols-3 gap-4 sm:gap-6 max-w-xl mx-auto"
          >
            <motion.div whileHover={{ y: -4, scale: 1.02 }} className="text-center glass p-4 rounded-xl shadow-soft hover:shadow-glow transition-all duration-300">
              <div className="text-3xl sm:text-4xl font-bold text-gradient mb-1"><AnimatedCounter value={1.6} suffix="M+" decimals={1} /></div>
              <div className="text-sm text-muted-foreground">Компаний</div>
            </motion.div>
            <motion.div whileHover={{ y: -4, scale: 1.02 }} className="text-center glass p-4 rounded-xl shadow-soft hover:shadow-glow transition-all duration-300">
              <div className="text-3xl sm:text-4xl font-bold text-gradient mb-1"><AnimatedCounter value={24} suffix="/7" /></div>
              <div className="text-sm text-muted-foreground">Доступность</div>
            </motion.div>
            <motion.div whileHover={{ y: -4, scale: 1.02 }} className="text-center glass p-4 rounded-xl shadow-soft hover:shadow-glow transition-all duration-300 col-span-2 sm:col-span-1">
              <div className="text-3xl sm:text-4xl font-bold text-gradient mb-1"><AnimatedCounter value={99.9} suffix="%" decimals={1} /></div>
              <div className="text-sm text-muted-foreground">Точность</div>
            </motion.div>
          </motion.div>
        </div>
      </div>

      {/* Floating Cards */}
      <motion.div
        initial={{ opacity: 0, x: -50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.8, delay: 0.6 }}
        className="hidden lg:block absolute left-10 top-1/3 animate-float"
      >
        <div className="glass p-4 rounded-xl shadow-card hover:shadow-glow transition-shadow duration-300">
          <Building2 className="w-8 h-8 text-primary mb-2" />
          <p className="text-sm font-medium text-foreground">Реестр ЮЛ и ИП</p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, x: 50 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.8, delay: 0.7 }}
        className="hidden lg:block absolute right-10 bottom-1/3 animate-float"
        style={{ animationDelay: "1s" }}
      >
        <div className="glass p-4 rounded-xl shadow-card hover:shadow-glow transition-shadow duration-300">
          <Shield className="w-8 h-8 text-accent mb-2" />
          <p className="text-sm font-medium text-foreground">Безопасный API</p>
        </div>
      </motion.div>

      {/* Additional Decorative Elements */}
      <motion.div
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, delay: 0.8 }}
        className="hidden lg:block absolute right-20 top-20 animate-float"
        style={{ animationDelay: "2s" }}
      >
        <div className="w-16 h-16 gradient-primary rounded-2xl flex items-center justify-center shadow-glow">
          <Zap className="w-8 h-8 text-primary-foreground" />
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, delay: 0.9 }}
        className="hidden lg:block absolute left-20 bottom-20 animate-float"
        style={{ animationDelay: "3s" }}
      >
        <div className="w-12 h-12 bg-accent/20 rounded-full flex items-center justify-center shadow-soft backdrop-blur-sm">
          <div className="w-6 h-6 bg-accent rounded-full animate-pulse" />
        </div>
      </motion.div>
    </section>
  );
};
