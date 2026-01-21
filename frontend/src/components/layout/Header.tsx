import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";
import { Link } from "react-router-dom";

export const Header = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <motion.header 
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 glass"
    >
      <div className="container mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16 sm:h-20">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 sm:w-10 sm:h-10 gradient-primary rounded-lg flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-lg sm:text-xl">E</span>
            </div>
            <span className="text-xl sm:text-2xl font-bold text-foreground">ЕГР</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-8">
            <Link to="/dashboard" className="text-muted-foreground hover:text-foreground transition-colors">
              Главная
            </Link>
            <Link to="/search" className="text-muted-foreground hover:text-foreground transition-colors">
              Поиск
            </Link>
            <Link to="/references" className="text-muted-foreground hover:text-foreground transition-colors">
              Справочники
            </Link>
          </nav>

          {/* Mobile Menu Button */}
          <button 
            className="md:hidden p-2"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
          >
            {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden py-4 border-t border-border"
          >
            <nav className="flex flex-col gap-4">
              <Link to="/dashboard" className="text-muted-foreground hover:text-foreground transition-colors py-2">
                Главная
              </Link>
              <Link to="/search" className="text-muted-foreground hover:text-foreground transition-colors py-2">
                Поиск
              </Link>
              <Link to="/references" className="text-muted-foreground hover:text-foreground transition-colors py-2">
                Справочники
              </Link>
            </nav>
          </motion.div>
        )}
      </div>
    </motion.header>
  );
};
