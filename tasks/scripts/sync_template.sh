source ./tasks/shims/install_backend

template_url="https://bitbucket.org/tonkintaylor/python-template"
copier_version="9.4.1"

# N.B. we don't use copier update here because it doesn't play nicely with dynamic package versions
if [ -f "README.md" ]; then
    rm README.md
fi
if ! uvx --python 3.13 copier@$copier_version copy "git+$template_url" . --trust --vcs-ref master
then
    echo "Error: Could not copy the template repository"
    exit
fi
