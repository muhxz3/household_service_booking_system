document.addEventListener('DOMContentLoaded', () => {
    // 1. Page Fade-In on Load
    document.body.style.opacity = '0';
    document.body.style.transition = 'opacity 0.4s ease-in-out';
    requestAnimationFrame(() => {
        document.body.style.opacity = '1';
    });

    // 2. Enhanced Scroll Reveal Logic
    const reveal = () => {
        const reveals = document.querySelectorAll(".reveal, .login-box, .service-card, .admin-card");
        reveals.forEach(el => {
            const windowHeight = window.innerHeight;
            const elementTop = el.getBoundingClientRect().top;
            const elementVisible = 100;
            if (elementTop < windowHeight - elementVisible) {
                el.classList.add("active");
            }
        });
    };
    window.addEventListener("scroll", reveal);
    reveal(); // Initial check

    // 3. Button Ripple Effect (Material Design style)
    document.querySelectorAll('.btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const ripple = document.createElement('span');
            ripple.className = 'ripple-effect';
            ripple.style.left = `${x}px`;
            ripple.style.top = `${y}px`;
            
            this.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    });

    // 4. Form Submission Loading States
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.classList.contains('no-loader')) {
                submitBtn.classList.add('loading');
                submitBtn.innerHTML = '<div class="spinner" style="width:16px; height:16px; border-width:2px; margin:0 auto;"></div>';
                submitBtn.style.pointerEvents = 'none';
            }
        });
    });
});