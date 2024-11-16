// Hide flash message after 1 second (1000 milliseconds)
window.onload = function() {
    setTimeout(function() {
        const flashMessage = document.getElementById('flash-message');
        if (flashMessage) {
            flashMessage.style.display = 'none';
        }
    }, 2000);
};
// Ensure the buttons are working correctly for increasing and decreasing shares
document.getElementById("increase-shares").addEventListener("click", function() {
    var sharesInput = document.getElementById("shares");
    sharesInput.value = parseInt(sharesInput.value) + 1; // Increase the share number
});

document.getElementById("decrease-shares").addEventListener("click", function() {
    var sharesInput = document.getElementById("shares");
    if (sharesInput.value > 1) {
        sharesInput.value = parseInt(sharesInput.value) - 1; // Decrease the share number
    }
});
