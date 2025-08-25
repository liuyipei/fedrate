// Client-side JavaScript for the FedRate Agent Workflow Visualization

document.addEventListener('DOMContentLoaded', function() {
    // Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                window.scrollTo({
                    top: targetElement.offsetTop - 70,
                    behavior: 'smooth'
                });
            }
        });
    });
    
    // Add animation to cards when they come into view
    const cards = document.querySelectorAll('.card');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = 1;
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1 });
    
    cards.forEach(card => {
        card.style.opacity = 0;
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        observer.observe(card);
    });
    
    // Add click event to source cards to expand snippets
    const sourceCards = document.querySelectorAll('.source-card');
    
    sourceCards.forEach(card => {
        const snippet = card.querySelector('.source-snippet');
        if (snippet && snippet.textContent.length > 150) {
            const fullText = snippet.textContent;
            const shortText = fullText.substring(0, 150) + '...';
            
            snippet.textContent = shortText;
            
            const expandBtn = document.createElement('button');
            expandBtn.className = 'btn btn-link p-0';
            expandBtn.textContent = 'Show more';
            expandBtn.style.fontSize = '0.8rem';
            
            expandBtn.addEventListener('click', function(e) {
                e.preventDefault();
                if (snippet.textContent.includes('...')) {
                    snippet.textContent = fullText;
                    expandBtn.textContent = 'Show less';
                } else {
                    snippet.textContent = shortText;
                    expandBtn.textContent = 'Show more';
                }
            });
            
            card.querySelector('.card-body').appendChild(expandBtn);
        }
    });
});
