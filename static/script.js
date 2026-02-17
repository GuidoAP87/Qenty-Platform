/* =========================================
   VARITA MÁGICA (INTERACTIVIDAD GLOBAL)
   ========================================= */

document.addEventListener('DOMContentLoaded', function() {
    
    // --- 1. POLVO MÁGICO (Sigue al cursor en TODAS las páginas) ---
    document.addEventListener('mousemove', function(e) {
        let body = document.querySelector('body');
        let star = document.createElement('span');
        
        // Estilos de la estrella
        star.style.position = 'absolute';
        star.style.left = e.pageX + 'px';
        star.style.top = e.pageY + 'px';
        star.style.width = 3 + Math.random() * 5 + 'px'; // Tamaño variable
        star.style.height = star.style.width;
        star.style.borderRadius = '50%';
        star.style.pointerEvents = 'none'; // Para poder hacer click a través de ellas
        star.style.opacity = '0.9';
        star.style.zIndex = '9999';
        star.style.background = '#FFD700'; // Color Dorado
        star.style.boxShadow = '0 0 8px #FFD700, 0 0 15px #DAA520'; 
        
        body.appendChild(star);

        // Movimiento aleatorio al caer
        let directionX = Math.random() * 2 - 1;
        let directionY = Math.random() * 3 - 0.5;
        let speed = 0.02 + Math.random() * 0.03;

        // Animación de caída y desaparición
        let animation = setInterval(() => {
            star.style.top = (parseFloat(star.style.top) + directionY) + 'px';
            star.style.left = (parseFloat(star.style.left) + directionX) + 'px';
            star.style.opacity = parseFloat(star.style.opacity) - speed;
            
            // Cuando es invisible, la borramos de la memoria
            if(star.style.opacity <= 0) { 
                clearInterval(animation); 
                star.remove(); 
            }
        }, 20);
    });

    // --- 2. CÁLCULO DE FASE LUNAR (Solo si existe el widget) ---
    const moonIcon = document.getElementById('mainMoonIcon');
    
    if (moonIcon) { // Verificamos si estamos en la Home
        function getMoonPhase() {
            const newMoonRef = new Date(2024, 0, 11); 
            const lunarCycle = 29.53058867;
            const now = new Date();
            const diffTime = Math.abs(now - newMoonRef);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
            const phaseDay = diffDays % lunarCycle;
            
            let icon, text, phaseIndex;
            
            // Lógica de fases
            if (phaseDay < 1) { icon = "🌑"; text = "Luna Nueva"; phaseIndex = 0; }
            else if (phaseDay < 7.4) { icon = "🌒"; text = "Creciente"; phaseIndex = 1; }
            else if (phaseDay < 8.4) { icon = "🌓"; text = "Cuarto Creciente"; phaseIndex = 2; }
            else if (phaseDay < 14.8) { icon = "🌔"; text = "Gibosa Creciente"; phaseIndex = 3; }
            else if (phaseDay < 15.8) { icon = "🌕"; text = "Luna Llena"; phaseIndex = 4; }
            else if (phaseDay < 22.1) { icon = "🌖"; text = "Gibosa Menguante"; phaseIndex = 5; }
            else if (phaseDay < 23.1) { icon = "🌗"; text = "Cuarto Menguante"; phaseIndex = 6; }
            else { icon = "🌘"; text = "Menguante"; phaseIndex = 7; }

            // Actualizar el HTML
            document.getElementById('mainMoonIcon').textContent = icon;
            document.getElementById('mainMoonText').textContent = text;
            
            // Iluminar la lunita correcta en la barra inferior
            for(let i=0; i<8; i++) { 
                let p = document.getElementById('p'+i);
                if(p) p.classList.remove('active'); 
            }
            let activeP = document.getElementById('p'+phaseIndex);
            if(activeP) activeP.classList.add('active');
        }
        
        getMoonPhase();
    }
});