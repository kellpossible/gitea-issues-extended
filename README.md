# Gitea Issues Extended

This project was small subset of the code I wrote for my undergraduate final
year software project.

This is a [Flask](http://flask.pocoo.org/) web application which connects to the
[gitea](https://gitea.io) git hosting service via a REST api in order to extract
data about a particular repository and its issue tracker and display it in 
alternative ways.

We used this software during our project to help us keep track of our progress,
and give an overview of the issues remaining in the issue tracker.

Currrently the two supported modes of operation are a kanban board, and a gantt
chart.

The project is currently untested with Gitea, because originally I designed it
for Gogs, and it still needs to be ported to Gitea, to ensure that it still
works even with the API changes since the Gitea project forked from Gogs.